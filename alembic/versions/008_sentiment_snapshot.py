"""Coverage sentiment per problem, append-only.

Revision ID: 008_sentiment_snapshot
Revises: 007_authority_seed
Create Date: 2026-08-05

Same append-only shape as score_snapshot: keyed (problem_id, at), readers take
the latest, and the history is what makes a trend computable later without a
second design.

`prompt_ver` and `model` are stored per row so a change in tone over time can
be told apart from a change in classifier — without them, re-running with a
new model looks like public opinion moving.

Scope is coverage sentiment only: how a problem is discussed in documents
already ingested. There is no per-person column here and no politician entity
in the schema.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "008_sentiment_snapshot"
down_revision: str | Sequence[str] | None = "007_authority_seed"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE sentiment_snapshot (
          problem_id  uuid NOT NULL REFERENCES problem(id) ON DELETE CASCADE,
          at          timestamptz NOT NULL DEFAULT now(),
          label       text NOT NULL CHECK (label IN ('negative', 'neutral', 'positive')),
          -- Documents behind the label, so a summary over one article is not
          -- read with the same weight as one over thirty.
          sample_size int NOT NULL CHECK (sample_size > 0),
          negative    int NOT NULL DEFAULT 0,
          neutral     int NOT NULL DEFAULT 0,
          positive    int NOT NULL DEFAULT 0,
          model       text NOT NULL,
          prompt_ver  text NOT NULL,
          PRIMARY KEY (problem_id, at)
        )
    """)
    op.execute("""
        CREATE INDEX sentiment_snapshot_problem_at_idx
          ON sentiment_snapshot (problem_id, at DESC)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS sentiment_snapshot_problem_at_idx")
    op.execute("DROP TABLE IF EXISTS sentiment_snapshot")
