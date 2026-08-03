# ruff: noqa: RUF001, S608
"""Seed known Greek public bodies into authority.

Revision ID: 007_authority_seed
Revises: 006_greek_snowball
Create Date: 2026-08-03

001_core.py created `authority` and `problem.authority_id`; nothing has ever
written a row to it, so every problem's authority_id has been NULL since the
table existed. Claims already name these bodies verbatim — ΕΥΑΘ appears
twice in real extracted data — but had nowhere to link to.

The ids here are fixed (uuid5, deterministic, not typed from memory) and
MUST match adapters/authority/__init__.py, which resolves free text to these
same primary keys without ever querying the database. Add a body in both
places, or not at all.

`jurisdiction` is left NULL for every row. A MultiPolygon boundary typed by
hand from memory would be exactly the kind of fabrication this project's
gazetteer work (topos-cli gazetteer refresh, sourced from OpenStreetMap) was
built to avoid — populate it later from an official boundary source, the
same way.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "007_authority_seed"
down_revision: str | None = "006_greek_snowball"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (id, name, level) — level values from domain.types.AuthorityLevel.
_AUTHORITIES = (
    ("27c9d268-35b6-5462-873f-93cb7894a51a", "ΕΥΑΘ", "utility"),
    ("0873a2dc-5dad-5350-85d5-09722a430de4", "ΔΕΔΔΗΕ", "utility"),
    ("bab806fa-1686-538b-98e2-03dd2075b95e", "ΟΑΣΘ", "utility"),
    ("dc6a6090-f08e-5695-945f-15803738efdd", "ΔΕΗ", "utility"),
    ("83eda05c-7c5b-52ec-80ed-e44c71a87d9f", "Δήμος Θεσσαλονίκης", "municipality"),
)


def upgrade() -> None:
    # Static, in-file data — not user input — so string-built SQL is safe
    # here despite the shape S608 flags (file-level noqa above).
    for authority_id, name, level in _AUTHORITIES:
        op.execute(
            "INSERT INTO authority (id, name, level) "
            f"VALUES ('{authority_id}'::uuid, '{name}', '{level}') "
            "ON CONFLICT (id) DO NOTHING"
        )


def downgrade() -> None:
    ids = ", ".join(f"'{authority_id}'::uuid" for authority_id, _, _ in _AUTHORITIES)
    op.execute(f"DELETE FROM authority WHERE id IN ({ids})")
