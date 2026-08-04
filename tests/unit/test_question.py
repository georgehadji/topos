# ruff: noqa: RUF001
"""Unit tests: parliamentary question drafting.

The load-bearing property is faithfulness: nothing may appear in the output
that is not in the brief. A minister answers this on the record.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from topos.domain.question import QuestionBrief, SourceCitation, render_question

_BRIEF = QuestionBrief(
    title="Καθυστέρηση αποκατάστασης πεζοδρομίων",
    category="pedestrian_hazard_remediation_delay",
    citations=(SourceCitation(uri="municipality://31h-05-08-2026.pdf", title="Πρακτικά ΔΣ"),),
    authority="Δήμος Θεσσαλονίκης",
    location="Τριανδρία",
    facts=("Παράταση της σύμβασης κατά δύο μήνες.",),
    budget_eur=Decimal("372000.00"),
    first_seen=date(2026, 2, 12),
    last_seen=date(2026, 8, 3),
    recurrence=3,
)


def test_draft_has_the_conventional_structure() -> None:
    out = render_question(_BRIEF)
    assert out.startswith("ΕΡΩΤΗΣΗ")
    assert "Προς:" in out
    assert "Θέμα:" in out
    assert "ερωτάται ο/η κ. Υπουργός:" in out
    assert "Πηγές:" in out


def test_every_citation_appears() -> None:
    out = render_question(_BRIEF)
    assert "municipality://31h-05-08-2026.pdf" in out
    assert "Πρακτικά ΔΣ" in out


def test_facts_appear_verbatim() -> None:
    assert "Παράταση της σύμβασης κατά δύο μήνες." in render_question(_BRIEF)


def test_budget_is_stated_with_its_exact_figure() -> None:
    assert "372,000.00" in render_question(_BRIEF)


def test_recurrence_is_stated_when_repeated() -> None:
    out = render_question(_BRIEF)
    assert "3 φορές" in out
    assert "μεμονωμένο περιστατικό" in out


def test_recurrence_clause_absent_when_seen_once() -> None:
    out = render_question(QuestionBrief(title="Τ", category="c", citations=(), recurrence=1))
    assert "φορές" not in out


def test_no_numeral_appears_that_is_not_in_the_brief() -> None:
    """The faithfulness property. Any number in the draft must trace to a
    field — dates, the budget, recurrence, or the question numbering."""
    out = render_question(_BRIEF)
    allowed = {"372", "000", "00", "2026", "02", "12", "08", "03", "3", "05", "31", "2"}
    allowed |= {str(n) for n in range(1, 10)}  # numbered asks and citation markers
    for numeral in re.findall(r"\d+", out):
        assert numeral in allowed, f"unexplained numeral {numeral!r} in draft"


def test_absent_fields_omit_their_lines_rather_than_guessing() -> None:
    bare = QuestionBrief(title="Πρόβλημα", category="c", citations=())
    out = render_question(bare)
    assert "προϋπολογισμός" not in out
    assert "αρμόδιος φορέας προκύπτει" not in out
    assert "καταγράφεται από" not in out
    assert "None" not in out


def test_missing_ministry_falls_back_to_a_neutral_addressee() -> None:
    out = render_question(QuestionBrief(title="Τ", category="c", citations=()))
    assert "αρμόδιο Υπουργό" in out


def test_location_appears_in_the_subject_line() -> None:
    subject = render_question(_BRIEF).split("\n")[3]
    assert "Τριανδρία" in subject


def test_budget_question_only_when_a_budget_exists() -> None:
    with_budget = render_question(_BRIEF)
    without = render_question(QuestionBrief(title="Τ", category="c", citations=()))
    assert "απορροφηθεί" in with_budget
    assert "απορροφηθεί" not in without


def test_extra_questions_are_appended() -> None:
    brief = QuestionBrief(
        title="Τ", category="c", citations=(), extra_questions=("Ειδική ερώτηση;",)
    )
    assert "Ειδική ερώτηση;" in render_question(brief)


def test_rendering_is_deterministic() -> None:
    assert render_question(_BRIEF) == render_question(_BRIEF)


def test_single_date_renders_one_clause_not_a_range() -> None:
    brief = QuestionBrief(
        title="Τ",
        category="c",
        citations=(),
        first_seen=date(2026, 8, 3),
        last_seen=date(2026, 8, 3),
    )
    out = render_question(brief)
    assert "έως" not in out
    assert "2026-08-03" in out
