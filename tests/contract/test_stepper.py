"""Contract test: two concurrent workers never claim the same pipeline row.

Requires the docker-compose stack running (`docker compose up -d`).
Mark: pytest -m contract
"""

from __future__ import annotations

import asyncio
import os
import socket
import subprocess
import uuid
from collections.abc import AsyncGenerator

import asyncpg
import pytest

from topos.adapters.db.pipeline_repo import PipelineRepo
from topos.domain.pipeline_fsm import StepOutcome, next_state
from topos.domain.types import ArtifactId, PipelineState

pytestmark = pytest.mark.contract


def _find_pg_host() -> str:
    """Find the IP where docker-compose postgres is reachable."""
    try:
        result = subprocess.run(
            ["wsl", "--", "ip", "-4", "addr", "show", "eth0"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        for line in result.stdout.splitlines():
            if "inet " in line:
                ip = line.strip().split()[1].split("/")[0]
                s = socket.socket()
                s.settimeout(1)
                try:
                    s.connect((ip, 5432))
                    s.close()
                    return ip
                except (OSError, TimeoutError):
                    pass
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    host = os.environ.get("TOPOS_TEST_PG_HOST")
    if host:
        return host

    return "127.0.0.1"


def _dsn() -> str:
    """Where the contract-test PostgreSQL lives.

    An explicit DSN wins and skips discovery entirely — it is the only way to
    reach a Postgres on a non-default port (e.g. when 5432 on the host is
    already taken by another instance). Same env-first shape as test_blob.py.
    """
    explicit = os.environ.get("TOPOS_TEST_PG_DSN")
    if explicit:
        return explicit
    return f"postgresql://topos:devonly@{_find_pg_host()}:5432/topos"


DSN = _dsn()


@pytest.fixture(autouse=True)
async def _cleanup() -> None:
    """Delete all test rows between tests."""
    conn = await asyncpg.connect(DSN)
    try:
        for src in ("test", "diavgeia", "fek", "deddhe"):
            await conn.execute(
                "DELETE FROM problem_claim WHERE claim_id IN"
                " (SELECT id FROM claim WHERE artifact_id IN"
                "  (SELECT id FROM artifact WHERE source_id = $1))",
                src,
            )
            await conn.execute(
                "DELETE FROM claim WHERE artifact_id IN"
                " (SELECT id FROM artifact WHERE source_id = $1)",
                src,
            )
            await conn.execute(
                "DELETE FROM extraction_run WHERE artifact_id IN"
                " (SELECT id FROM artifact WHERE source_id = $1)",
                src,
            )
            await conn.execute(
                "DELETE FROM chunk WHERE artifact_id IN"
                " (SELECT id FROM artifact WHERE source_id = $1)",
                src,
            )
            await conn.execute(
                "DELETE FROM document WHERE artifact_id IN"
                " (SELECT id FROM artifact WHERE source_id = $1)",
                src,
            )
            await conn.execute(
                "DELETE FROM pipeline WHERE artifact_id IN"
                " (SELECT id FROM artifact WHERE source_id = $1)",
                src,
            )
            await conn.execute("DELETE FROM artifact WHERE source_id = $1", src)
            await conn.execute(
                "DELETE FROM problem WHERE id NOT IN (SELECT problem_id FROM problem_claim)"
            )
    finally:
        await conn.close()


@pytest.fixture
async def conn() -> AsyncGenerator[asyncpg.Connection, None]:
    c = await asyncpg.connect(DSN)
    yield c
    await c.close()


@pytest.fixture
async def repo(conn: asyncpg.Connection) -> AsyncGenerator[PipelineRepo, None]:
    pool = await asyncpg.create_pool(DSN, min_size=1, max_size=1)
    r = PipelineRepo(pool)
    yield r
    await pool.close()


async def _ensure_source(conn: asyncpg.Connection) -> None:
    await conn.execute(
        """
        INSERT INTO source (id, kind, config, cadence, rights)
        VALUES ('test', 'test', '{}', interval '1 day', '{}')
        ON CONFLICT DO NOTHING
        """
    )


async def _insert_artifact(conn: asyncpg.Connection, artifact_id: ArtifactId) -> None:
    await _ensure_source(conn)
    await conn.execute(
        """
        INSERT INTO artifact (id, source_id, uri, sha256, blob_key, mime, bytes, fetched_at)
        VALUES ($1::uuid, 'test', 'test://' || $1::text, decode('00', 'hex'),
                'test', 'text/plain', 0, now())
        ON CONFLICT DO NOTHING
        """,
        artifact_id,
    )


async def _insert_pipeline(
    conn: asyncpg.Connection,
    artifact_id: ArtifactId,
    *,
    state: str = "fetched",
) -> None:
    await conn.execute(
        """
        INSERT INTO pipeline (artifact_id, state, run_after)
        VALUES ($1, $2::pipe_state, now() - interval '10 seconds')
        ON CONFLICT (artifact_id) DO UPDATE
          SET state = $2::pipe_state, run_after = now() - interval '10 seconds', locked_until = NULL, attempts = 0
        """,
        artifact_id,
        state,
    )


# ── Tests ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_claim_next_returns_none_when_queue_empty(repo: PipelineRepo) -> None:
    row = await repo.claim_next()
    assert row is None


@pytest.mark.asyncio
async def test_claim_next_claims_one_ready_row(repo: PipelineRepo) -> None:
    artifact_id = ArtifactId(uuid.uuid4())
    await _insert_artifact(repo._pool, artifact_id)
    await _insert_pipeline(repo._pool, artifact_id, state="fetched")

    row = await repo.claim_next()
    assert row is not None
    assert row.artifact_id == artifact_id
    assert row.state == PipelineState.FETCHED
    assert row.attempts >= 1
    assert row.locked_until is not None


@pytest.mark.asyncio
async def test_skipped_when_locked(repo: PipelineRepo, conn: asyncpg.Connection) -> None:
    a1 = ArtifactId(uuid.uuid4())
    a2 = ArtifactId(uuid.uuid4())

    await _insert_artifact(conn, a1)
    await _insert_artifact(conn, a2)
    await _insert_pipeline(conn, a1, state="fetched")
    await _insert_pipeline(conn, a2, state="fetched")

    row1 = await repo.claim_next()
    assert row1 is not None
    claimed_id = row1.artifact_id

    row2 = await repo.claim_next()
    if row2 is not None:
        assert row2.artifact_id != claimed_id, f"SKIP LOCKED violated: both claims got {claimed_id}"


@pytest.mark.asyncio
async def test_concurrent_workers_never_claim_same_row(
    conn: asyncpg.Connection,
) -> None:
    pool = await asyncpg.create_pool(DSN, min_size=5, max_size=10)
    repo = PipelineRepo(pool)

    N_ROWS = 20
    N_WORKERS = 10

    artifact_ids = [ArtifactId(uuid.uuid4()) for _ in range(N_ROWS)]

    for aid in artifact_ids:
        await _insert_artifact(conn, aid)
        await _insert_pipeline(conn, aid, state="fetched")

    claimed: set[ArtifactId] = set()
    lock = asyncio.Lock()

    async def worker() -> None:
        while True:
            row = await repo.claim_next()
            if row is None:
                async with lock:
                    if len(claimed) >= N_ROWS:
                        return
                await asyncio.sleep(0.005)
                continue
            async with lock:
                assert row.artifact_id not in claimed, f"DUPLICATE CLAIM: {row.artifact_id}"
                claimed.add(row.artifact_id)

    tasks = [asyncio.create_task(worker()) for _ in range(N_WORKERS)]
    await asyncio.gather(*tasks)

    assert len(claimed) == N_ROWS, f"Expected {N_ROWS} unique claims, got {len(claimed)}"
    await pool.close()


@pytest.mark.asyncio
async def test_advance_transitions_state(repo: PipelineRepo) -> None:
    artifact_id = ArtifactId(uuid.uuid4())
    # Use repo._pool instead of conn to ensure absolute transaction visibility
    await _insert_artifact(repo._pool, artifact_id)
    await _insert_pipeline(repo._pool, artifact_id, state="fetched")

    row = await repo.claim_next()
    assert row is not None
    assert row.artifact_id == artifact_id

    outcome = StepOutcome(next_state=PipelineState.TEXTIFIED)
    await repo.advance(row.artifact_id, from_state=row.state, outcome=outcome)

    updated = await repo._pool.fetchrow(
        "SELECT state, locked_until FROM pipeline WHERE artifact_id = $1::uuid",
        artifact_id,
    )
    assert updated["state"] == "textified"
    assert updated["locked_until"] is None


@pytest.mark.asyncio
async def test_failure_parks_after_max_attempts(
    repo: PipelineRepo, conn: asyncpg.Connection
) -> None:
    artifact_id = ArtifactId(uuid.uuid4())
    await _insert_artifact(conn, artifact_id)
    await _insert_pipeline(conn, artifact_id, state="fetched")

    for _ in range(5):
        row = await repo.claim_next()
        assert row is not None
        outcome = next_state(row.state, ok=False, attempts=row.attempts)
        await repo.advance(
            row.artifact_id, from_state=row.state, outcome=outcome, error="test failure"
        )
        if outcome.park:
            break
        # Reset run_after so the next claim can pick it up immediately
        await conn.execute(
            "UPDATE pipeline SET run_after = now() WHERE artifact_id = $1::uuid",
            artifact_id,
        )

    final = await conn.fetchrow(
        "SELECT state FROM pipeline WHERE artifact_id = $1::uuid", artifact_id
    )
    assert final["state"] == "parked"
