"""extraction_run.cost_eur: NOT NULL DEFAULT 0 -> nullable.

Revision ID: 009_nullable_cost_eur
Revises: 008_sentiment_snapshot
Create Date: 2026-08-07

See ADR-014. Telemetry inserted the literal 0 for every call regardless of
whether a price was known, which meant "priced at zero" and "unpriced,
unknown" were the same row. BudgetGuard sums cost_eur to enforce the monthly
ceiling, so that ambiguity meant the ceiling could never distinguish real free
usage from spend it simply never learned to price — it has been permanently
inert.

NULL now means "not priced" and SUM(cost_eur) (Postgres SUM ignores NULL)
correctly excludes those rows from the budget check rather than silently
counting them as free.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "009_nullable_cost_eur"
down_revision: str | Sequence[str] | None = "008_sentiment_snapshot"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE extraction_run ALTER COLUMN cost_eur DROP DEFAULT")
    op.execute("ALTER TABLE extraction_run ALTER COLUMN cost_eur DROP NOT NULL")


def downgrade() -> None:
    # Existing NULL rows become 0 — indistinguishable from priced-at-zero
    # again, which is exactly the ambiguity this migration removes. Accepted
    # as the cost of a downgrade path; upgrade is not meant to be reversed
    # once real cost data has accumulated.
    op.execute("UPDATE extraction_run SET cost_eur = 0 WHERE cost_eur IS NULL")
    op.execute("ALTER TABLE extraction_run ALTER COLUMN cost_eur SET NOT NULL")
    op.execute("ALTER TABLE extraction_run ALTER COLUMN cost_eur SET DEFAULT 0")
