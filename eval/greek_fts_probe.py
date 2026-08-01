# ruff: noqa: T201, E501, RUF001, S607
"""Greek FTS probe: comparing `greek_cfg` vs `simple` search recall.

Generates Greek text samples with various grammatical inflections/declensions,
runs search queries using the Greek stemmer (greek_cfg) vs the standard simple configuration,
and measures search recall metrics.
"""

from __future__ import annotations

import asyncio

import asyncpg

from topos.config import get_settings


async def main() -> None:
    settings = get_settings()
    if not settings.db_dsn:
        print("Error: TOPOS_DB_DSN is not configured.")
        return

    # TOPOS_DB_DSN is the single source of truth, exactly as it is for the app
    # and the workers. Do not rewrite the host: that silently overrode an
    # explicitly configured port.
    dsn = settings.db_dsn
    print(f"Connecting to {dsn.rsplit('@', 1)[-1]}...")
    conn = await asyncpg.connect(dsn)

    try:
        # Create a temporary table for the evaluation
        await conn.execute("DROP TABLE IF EXISTS fts_eval")
        await conn.execute(
            """
            CREATE TABLE fts_eval (
                id serial PRIMARY KEY,
                text text NOT NULL
            )
            """
        )

        # We insert various inflected Greek nouns/adjectives
        # (e.g. nominative/genitive/accusative singular and plural)
        samples = [
            "Ο δήμαρχος υπέγραψε την απόφαση για τα έργα.",  # 0: δήμαρχος, απόφαση, έργα
            "Οι αποφάσεις των δημάρχων καθορίζουν το μέλλον της πόλης.",  # 1: αποφάσεις, δημάρχων
            "Το έργο αφορά την ανάπλαση της πλατείας.",  # 2: έργο
            "Εγκρίθηκαν οι χρηματοδοτήσεις για τα νέα έργα.",  # 3: έργα
            "Υποβολή αίτησης για τη χορήγηση άδειας.",  # 4: αίτησης, άδειας
            "Παραλάβαμε τις αιτήσεις και τις άδειες των πολιτών.",  # 5: αιτήσεις, άδειες
        ]

        await conn.executemany(
            "INSERT INTO fts_eval (text) VALUES ($1)",
            [(s,) for s in samples],
        )

        # Test cases: (query stem, expected matching sample indexes (0-based))
        test_cases = [
            ("δημαρχ", [0, 1]),  # should match "δήμαρχος" (0) and "δημάρχων" (1)
            ("αποφασ", [0, 1]),  # should match "απόφαση" (0) and "αποφάσεις" (1)
            ("εργ", [0, 2, 3]),  # should match "έργα" (0), "έργο" (2), "έργα" (3)
            ("αιτησ", [4, 5]),  # should match "αίτησης" (4), "αιτήσεις" (5)
            ("αδει", [4, 5]),  # should match "άδειας" (4), "άδειες" (5)
        ]

        print("\n=== GREEK FTS RECALL EVALUATION ===")
        print(f"{'Query Stem':<15} | {'greek_cfg Recall':<18} | {'simple Recall':<15}")
        print("-" * 55)

        greek_cfg_total_found = 0
        simple_total_found = 0
        total_expected = sum(len(expected) for _, expected in test_cases)

        for term, expected_idx in test_cases:
            # Query with greek_cfg (has unaccent first, then simple)
            rows_greek = await conn.fetch(
                """
                SELECT id, text FROM fts_eval
                WHERE to_tsvector('greek_cfg', text) @@ to_tsquery('greek_cfg', $1)
                """,
                f"{term}:*",
            )
            found_greek = [r["id"] - 1 for r in rows_greek]
            correct_greek = set(found_greek).intersection(expected_idx)
            greek_cfg_total_found += len(correct_greek)

            # Query with simple config (no unaccent, so accented queries won't match)
            rows_simple = await conn.fetch(
                """
                SELECT id, text FROM fts_eval
                WHERE to_tsvector('simple', text) @@ to_tsquery('simple', $1)
                """,
                f"{term}:*",
            )
            found_simple = [r["id"] - 1 for r in rows_simple]
            correct_simple = set(found_simple).intersection(expected_idx)
            simple_total_found += len(correct_simple)

            # Format recall percentage
            greek_recall = len(correct_greek) / len(expected_idx) * 100
            simple_recall = len(correct_simple) / len(expected_idx) * 100

            print(
                f"{term:<15} | {greek_recall:>5.1f}% ({len(correct_greek)}/{len(expected_idx)})"
                f"       | {simple_recall:>5.1f}% ({len(correct_simple)}/{len(expected_idx)})"
            )

        overall_greek_recall = (greek_cfg_total_found / total_expected) * 100
        overall_simple_recall = (simple_total_found / total_expected) * 100

        print("-" * 55)
        print(
            f"{'OVERALL RECALL':<15} | {overall_greek_recall:>17.1f}% | {overall_simple_recall:>14.1f}%"
        )
        print("===================================\n")

    finally:
        await conn.execute("DROP TABLE IF EXISTS fts_eval")
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
