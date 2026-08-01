"""Greek stemming: snowball replaces the hunspell dictionary.

Revision ID: 006_greek_snowball
Revises: 005_recommendation_approval
Create Date: 2026-08-01

002_greek_fts mapped `greek_cfg` to `el_gr_hunspell`, built from Debian's
hunspell-el. That dictionary cannot stem: its .dic is a fully expanded word
list — 828k entries, **zero** of which carry an affix flag — so none of the 189
SFX/PFX rules in the .aff file can ever fire. Every word resolved to itself and
fell through to `simple`. `greek_cfg` was doing accent folding and nothing else:

    δρόμου       -> 'δρομου'      δρόμος       -> 'δρομος'
    Θεσσαλονίκης -> 'θεσσαλονικης' Θεσσαλονίκη -> 'θεσσαλονικη'

A query for `ύδρευση` could not match an indexed `ύδρευσης`. Reordering the
mapping or unaccenting the dictionary does not help — the flags simply are not
there.

PostgreSQL 16 ships a Greek snowball stemmer. It folds inflection and strips
accents itself:

    δρόμου, δρόμος             -> 'δρομ'
    Θεσσαλονίκης, Θεσσαλονίκη  -> 'θεσσαλονικ'
    ύδρευσης, ύδρευση          -> 'υδρευσ'

`unaccent` is kept ahead of it so mixed-script content is normalised too.

`chunk.tsv` is GENERATED ... STORED, so existing rows hold lexemes produced by
the old chain. The column is dropped and re-added to force a recompute.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "006_greek_snowball"
down_revision: str | None = "005_recommendation_approval"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_MAPPED_TOKENS = "word, asciiword, hword, hword_part, hword_asciipart, asciihword"


def upgrade() -> None:
    op.execute(
        "CREATE TEXT SEARCH DICTIONARY el_gr_stem ("
        "  TEMPLATE = snowball,"
        "  Language = 'greek'"
        ")"
    )
    op.execute(
        "ALTER TEXT SEARCH CONFIGURATION greek_cfg"
        f"  ALTER MAPPING FOR {_MAPPED_TOKENS}"
        "  WITH unaccent, el_gr_stem, simple"
    )
    # Only safe once nothing in the configuration references it any more.
    op.execute("DROP TEXT SEARCH DICTIONARY IF EXISTS el_gr_hunspell")

    _recompute_chunk_tsv()


def downgrade() -> None:
    op.execute(
        "CREATE TEXT SEARCH DICTIONARY el_gr_hunspell ("
        "  TEMPLATE = ispell,"
        "  DictFile = el_gr,"
        "  AffFile = el_gr"
        ")"
    )
    op.execute(
        "ALTER TEXT SEARCH CONFIGURATION greek_cfg"
        f"  ALTER MAPPING FOR {_MAPPED_TOKENS}"
        "  WITH unaccent, el_gr_hunspell, simple"
    )
    op.execute("DROP TEXT SEARCH DICTIONARY IF EXISTS el_gr_stem")

    _recompute_chunk_tsv()


def _recompute_chunk_tsv() -> None:
    """Force every chunk.tsv to be regenerated under the current greek_cfg.

    ponytail: drop-and-re-add rewrites the whole table and rebuilds the GIN
    index. Fine at current scale (thousands of chunks). If `chunk` grows past
    the point where a full rewrite is an outage, switch tsv to a plain column
    maintained by a trigger and backfill it in batches.
    """
    op.execute("DROP INDEX IF EXISTS chunk_tsv_idx")
    op.execute("ALTER TABLE chunk DROP COLUMN IF EXISTS tsv")
    op.execute(
        "ALTER TABLE chunk ADD COLUMN tsv tsvector"
        "  GENERATED ALWAYS AS (to_tsvector('greek_cfg', text)) STORED"
    )
    op.execute("CREATE INDEX chunk_tsv_idx ON chunk USING gin (tsv)")
