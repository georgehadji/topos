"""Audit log table for tracking user actions.

Revision ID: 004_audit_log
Revises: 003_llm_cache
Create Date: 2026-07-23

Slice 1.11. Every write operation records: who did what, when, and the
before/after state.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "004_audit_log"
down_revision: str | None = "003_llm_cache"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE audit_log (
          id          bigserial PRIMARY KEY,
          actor       text NOT NULL,
          action      text NOT NULL,
          target_type text,
          target_id   text,
          payload     jsonb,
          ip          text,
          at          timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX ON audit_log (actor, at)")
    op.execute("CREATE INDEX ON audit_log (target_type, target_id)")
    # Retention: not auto-purged (audit logs are permanent by design)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS audit_log")
