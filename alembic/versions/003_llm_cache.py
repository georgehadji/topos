"""LLM cache table for prompt deduplication.

Revision ID: 003_llm_cache
Revises: 002_greek_fts
Create Date: 2026-07-23

Created by slice 0.10. Stores cached LLM responses keyed on
sha256(prompt + model + response_format).
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "003_llm_cache"
down_revision: str | None = "002_greek_fts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE llm_cache (
          cache_key    text PRIMARY KEY,
          response     jsonb NOT NULL,
          created_at   timestamptz NOT NULL DEFAULT now()
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS llm_cache")
