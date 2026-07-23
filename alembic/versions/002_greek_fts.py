"""Greek full-text search configuration + chunk.tsv column.

Revision ID: 002_greek_fts
Revises: 001_core
Create Date: 2026-07-23

Creates the `greek_cfg` text-search configuration that 001_core deliberately
deferred. Adds `chunk.tsv` as a GENERATED ALWAYS AS column and its GIN index.

Prerequisites (created in infra/postgres/init/00-extensions.sql):
  postgis, pgvector, pg_trgm, unaccent, btree_gin, pgcrypto

Prerequisites (installed in infra/postgres/Dockerfile):
  hunspell-el → el_gr.affix / el_gr.dict in tsearch_data

If hunspell-el is not installed, this migration still succeeds: it creates the
dictionary and config, but the dictionary will fall back to the `simple`
dictionary at query time. Measure quality with eval/greek_fts_probe.py (0.5).
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "002_greek_fts"
down_revision: str | None = "001_core"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── Text-search dictionary: hunspell el_GR ─────────────────────────────
    # Uses the .affix/.dict files installed by infra/postgres/Dockerfile into
    # pg_config --sharedir/tsearch_data/. If those files are missing, the
    # dictionary still creates but resolves nothing — greek_cfg falls through
    # to the `simple` mapping set below.
    op.execute("CREATE TEXT SEARCH DICTIONARY el_gr_hunspell ("
               "  TEMPLATE = ispell,"
               "  DictFile = el_gr,"
               "  AffFile = el_gr"
               ")")

    # ── Text-search configuration ──────────────────────────────────────────
    op.execute("CREATE TEXT SEARCH CONFIGURATION greek_cfg ("
               "  PARSER = default"
               ")")

    # Mapping: asciihword / hword / hword_part → unaccent first, then hunspell.
    # word / asciiword / hword_asciipart → unaccent first, then hunspell.
    # Everything else → simple (no stemming, but still searchable).
    # This is the chain described in ARCHITECTURE.md §Greek:
    #   unaccent + hunspell el_GR, with simple + trigram as fallback.
    op.execute("ALTER TEXT SEARCH CONFIGURATION greek_cfg"
               "  ALTER MAPPING FOR asciihword, hword, hword_part"
               "  WITH unaccent, el_gr_hunspell, simple")
    op.execute("ALTER TEXT SEARCH CONFIGURATION greek_cfg"
               "  ALTER MAPPING FOR word, asciiword, hword_asciipart"
               "  WITH unaccent, el_gr_hunspell, simple")

    # ── chunk.tsv: generated column (deferred from 001_core) ───────────────
    op.execute("ALTER TABLE chunk ADD COLUMN tsv tsvector"
               "  GENERATED ALWAYS AS (to_tsvector('greek_cfg', text)) STORED")
    op.execute("CREATE INDEX chunk_tsv_idx ON chunk USING gin (tsv)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS chunk_tsv_idx")
    op.execute("ALTER TABLE chunk DROP COLUMN IF EXISTS tsv")
    op.execute("DROP TEXT SEARCH CONFIGURATION IF EXISTS greek_cfg")
    op.execute("DROP TEXT SEARCH DICTIONARY IF EXISTS el_gr_hunspell")
