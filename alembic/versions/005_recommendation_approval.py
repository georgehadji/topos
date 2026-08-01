"""Recommendation approval columns on problem.

Revision ID: 005_recommendation_approval
Revises: 004_audit_log
Create Date: 2026-08-01

Slice 2.5. The recommendation workflow — service/recommendations.py,
interfaces/http/recommendations.py and the GraphQL schema — reads and writes
``problem.approved_by``, ``approved_at`` and ``exported_at``. 001_core never
created them, so every ``/api/recommendations`` request failed with
UndefinedColumnError and approve/reject/export were unreachable.

Additive and reversible: three nullable columns, no rewrite of existing rows.
See docs/adr/ADR-011-recommendation-approval-columns.md.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "005_recommendation_approval"
down_revision: str | None = "004_audit_log"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE problem ADD COLUMN IF NOT EXISTS approved_by text")
    op.execute("ALTER TABLE problem ADD COLUMN IF NOT EXISTS approved_at timestamptz")
    op.execute("ALTER TABLE problem ADD COLUMN IF NOT EXISTS exported_at timestamptz")
    # Approved problems are the working set for the export queue; the partial
    # index keeps that scan small as `problem` grows.
    op.execute(
        "CREATE INDEX IF NOT EXISTS problem_approved_at_idx"
        " ON problem (approved_at) WHERE approved_at IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS problem_approved_at_idx")
    op.execute("ALTER TABLE problem DROP COLUMN IF EXISTS exported_at")
    op.execute("ALTER TABLE problem DROP COLUMN IF EXISTS approved_at")
    op.execute("ALTER TABLE problem DROP COLUMN IF EXISTS approved_by")
