"""Core schema: registry, pipeline, text, claims, problems, graph, ER, review.

Revision ID: 001_core
Revises: None
Create Date: 2026-07-23

Prerequisite (not created here — see infra/postgres/init/00-extensions.sql and
the CI bootstrap step in .github/workflows/ci.yml): postgis, pg_trgm, unaccent,
btree_gin, pgcrypto. `vector` additionally required before 002_greek_fts is
superseded by anything touching problem_vec (known CI gap, tracked in
docs/PROGRESS.md).

`chunk.tsv` and its GIN index are deliberately NOT created here. They depend on
the `greek_cfg` text-search configuration, which does not exist until
002_greek_fts.py. Bundling them here would make 001 unrunnable before 0.5 is
done — see ARCHITECTURE.md > Data access and docs/PROGRESS.md slice 0.4/0.5.

Table order is FK-dependency order, not the reading order in
docs/IMPLEMENTATION_PLAN.md §6 (that doc defines `authority` after `problem`,
which cannot execute — `problem.authority_id` references it).

NOTE: Each op.execute() contains exactly one SQL statement. asyncpg (the driver used
by alembic/env.py) does not support multiple commands in a single execute().
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "001_core"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── Registry ────────────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE source (
          id            text PRIMARY KEY,
          kind          text NOT NULL,
          config        jsonb NOT NULL,
          cadence       interval NOT NULL,
          rights        jsonb NOT NULL,
          reliability   numeric(3,2) NOT NULL DEFAULT 0.50,
          enabled       boolean NOT NULL DEFAULT true,
          last_ok_at    timestamptz,
          last_error    text,
          created_at    timestamptz NOT NULL DEFAULT now()
        )
    """)

    # ── Immutable artifacts (WORM once cited) ──────────────────────────────
    op.execute("""
        CREATE TABLE artifact (
          id            uuid PRIMARY KEY,
          source_id     text NOT NULL REFERENCES source(id),
          uri           text NOT NULL,
          sha256        bytea NOT NULL,
          blob_key      text NOT NULL,
          mime          text NOT NULL,
          bytes         bigint NOT NULL,
          fetched_at    timestamptz NOT NULL,
          observed_seq  int NOT NULL DEFAULT 1,
          superseded_by uuid REFERENCES artifact(id),
          UNIQUE (source_id, uri, sha256)
        )
    """)
    op.execute("CREATE INDEX ON artifact (source_id, fetched_at DESC)")

    # ── Pipeline (ADR-004) ──────────────────────────────────────────────────
    op.execute("""
        CREATE TYPE pipe_state AS ENUM (
          'fetched', 'textified', 'chunked', 'extracted', 'geocoded',
          'resolved', 'indexed', 'done', 'parked')
    """)
    op.execute("""
        CREATE TABLE pipeline (
          artifact_id   uuid PRIMARY KEY REFERENCES artifact(id),
          state         pipe_state NOT NULL DEFAULT 'fetched',
          attempts      smallint NOT NULL DEFAULT 0,
          run_after     timestamptz NOT NULL DEFAULT now(),
          locked_until  timestamptz,
          last_error    text,
          updated_at    timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX ON pipeline (state, run_after) WHERE state <> 'done'")

    # ── Text ─────────────────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE document (
          artifact_id   uuid PRIMARY KEY REFERENCES artifact(id),
          lang          text NOT NULL,
          text          text NOT NULL,
          text_method   text NOT NULL,
          quality       numeric(3,2),
          pages         jsonb
        )
    """)
    op.execute("""
        CREATE TABLE chunk (
          id            bigserial PRIMARY KEY,
          artifact_id   uuid NOT NULL REFERENCES artifact(id),
          ord           int NOT NULL,
          span          int4range NOT NULL,
          text          text NOT NULL,
          UNIQUE (artifact_id, ord)
        )
    """)
    op.execute("CREATE INDEX ON chunk USING gin (text gin_trgm_ops)")

    # ── Provenance of every LLM/model invocation ────────────────────────────
    op.execute("""
        CREATE TABLE extraction_run (
          id            uuid PRIMARY KEY,
          artifact_id   uuid NOT NULL REFERENCES artifact(id),
          prompt_ver    text NOT NULL,
          model         text NOT NULL,
          params        jsonb NOT NULL,
          started_at    timestamptz NOT NULL,
          cost_eur      numeric(10,6) NOT NULL DEFAULT 0,
          tokens_in     int,
          tokens_out    int,
          ok            boolean NOT NULL
        )
    """)

    # ── Claims: atomic, immutable, span-anchored ────────────────────────────
    op.execute("""
        CREATE TABLE claim (
          id            uuid PRIMARY KEY,
          run_id        uuid NOT NULL REFERENCES extraction_run(id),
          artifact_id   uuid NOT NULL REFERENCES artifact(id),
          span          int4range NOT NULL,
          predicate     text NOT NULL,
          value         jsonb NOT NULL,
          confidence    numeric(3,2) NOT NULL,
          retracted_at  timestamptz
        )
    """)
    op.execute("CREATE INDEX ON claim (artifact_id) WHERE retracted_at IS NULL")

    # ── Authority = office, never a person (constraint L1) ──────────────────
    op.execute("""
        CREATE TABLE authority (
          id            uuid PRIMARY KEY,
          name          text NOT NULL,
          level         text NOT NULL,
          jurisdiction  geometry(MultiPolygon, 4326),
          parent_id     uuid REFERENCES authority(id)
        )
    """)

    # ── Problems: event-sourced (ADR-007) ────────────────────────────────────
    op.execute("""
        CREATE TABLE problem (
          id            uuid PRIMARY KEY,
          title         text NOT NULL,
          category      text NOT NULL,
          status        text NOT NULL,
          geom          geometry(Point, 4326),
          geo_conf      numeric(3,2),
          authority_id  uuid REFERENCES authority(id),
          first_seen    timestamptz NOT NULL,
          last_seen     timestamptz NOT NULL,
          version       int NOT NULL DEFAULT 1
        )
    """)
    op.execute("CREATE INDEX ON problem USING gist (geom)")

    op.execute("""
        CREATE TABLE problem_event (
          id            bigserial PRIMARY KEY,
          problem_id    uuid NOT NULL,
          seq           int NOT NULL,
          kind          text NOT NULL,
          payload       jsonb NOT NULL,
          actor         text NOT NULL,
          at            timestamptz NOT NULL DEFAULT now(),
          UNIQUE (problem_id, seq)
        )
    """)
    op.execute("""
        CREATE TABLE problem_claim (
          problem_id    uuid NOT NULL,
          claim_id      uuid NOT NULL,
          role          text NOT NULL,
          weight        numeric(3,2) NOT NULL,
          PRIMARY KEY (problem_id, claim_id)
        )
    """)

    # ── Graph edges (ADR-002: recursive CTE traversal) ──────────────────────
    op.execute("""
        CREATE TABLE edge (
          src_type      text NOT NULL,
          src_id        uuid NOT NULL,
          rel           text NOT NULL,
          dst_type      text NOT NULL,
          dst_id        uuid NOT NULL,
          valid         tstzrange NOT NULL DEFAULT tstzrange(now(), NULL),
          claim_id      uuid REFERENCES claim(id),
          PRIMARY KEY (src_type, src_id, rel, dst_type, dst_id)
        )
    """)
    op.execute("CREATE INDEX ON edge (dst_type, dst_id, rel)")

    # ── Derived-layer vectors only (ADR-010) ────────────────────────────────
    op.execute("""
        CREATE TABLE problem_vec (
          problem_id    uuid PRIMARY KEY REFERENCES problem(id),
          emb           halfvec(1024) NOT NULL,
          model         text NOT NULL
        )
    """)
    op.execute("CREATE INDEX ON problem_vec USING hnsw (emb halfvec_cosine_ops)")

    # ── Entity resolution, reversible (Command pattern) ─────────────────────
    op.execute("""
        CREATE TABLE er_decision (
          id            bigserial PRIMARY KEY,
          a_id          uuid NOT NULL,
          b_id          uuid NOT NULL,
          verdict       text NOT NULL,
          score         numeric(4,3) NOT NULL,
          features      jsonb NOT NULL,
          actor         text NOT NULL,
          reverted_by   bigint REFERENCES er_decision(id),
          at            timestamptz NOT NULL DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE review_task (
          id            uuid PRIMARY KEY,
          kind          text NOT NULL,
          payload       jsonb NOT NULL,
          priority      int NOT NULL DEFAULT 100,
          claimed_by    text,
          claimed_until timestamptz,
          resolved_at   timestamptz,
          resolution    jsonb
        )
    """)
    op.execute("CREATE INDEX ON review_task (priority, id) WHERE resolved_at IS NULL")

    op.execute("""
        CREATE TABLE score_snapshot (
          problem_id    uuid NOT NULL,
          at            timestamptz NOT NULL,
          scores        jsonb NOT NULL,
          formula_ver   text NOT NULL,
          PRIMARY KEY (problem_id, at)
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS score_snapshot")
    op.execute("DROP TABLE IF EXISTS review_task")
    op.execute("DROP TABLE IF EXISTS er_decision")
    op.execute("DROP TABLE IF EXISTS problem_vec")
    op.execute("DROP TABLE IF EXISTS edge")
    op.execute("DROP TABLE IF EXISTS problem_claim")
    op.execute("DROP TABLE IF EXISTS problem_event")
    op.execute("DROP TABLE IF EXISTS problem")
    op.execute("DROP TABLE IF EXISTS authority")
    op.execute("DROP TABLE IF EXISTS claim")
    op.execute("DROP TABLE IF EXISTS extraction_run")
    op.execute("DROP TABLE IF EXISTS chunk")
    op.execute("DROP TABLE IF EXISTS document")
    op.execute("DROP TABLE IF EXISTS pipeline")
    op.execute("DROP TYPE IF EXISTS pipe_state")
    op.execute("DROP TABLE IF EXISTS artifact")
    op.execute("DROP TABLE IF EXISTS source")
