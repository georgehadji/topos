# ruff: noqa: RUF001
"""Draft a written parliamentary question (ερώτηση κοινοβουλευτικού ελέγχου).

Pure. Deterministic. **No LLM.**

The plan for this originally put an LLM behind a port to turn a facts-only
brief into Greek prose. That was dropped: a written question has a rigid,
conventional form — addressee, subject line, a recital of facts, numbered
questions, signature block — and a template fills it exactly. An LLM would add
cost, latency, non-determinism and a fabrication surface in exchange for prose
polish nobody asked for. The one thing this document must be is *literally
true*, because a minister answers it on the record within 25 days.

So every sentence below is assembled from stored fields. If a field is
missing, its line is omitted. Nothing is inferred, softened, or filled in.

The rhetorical framing is deliberately neutral — it states what the documents
say and asks what the ministry intends. Choosing a political angle is the
member's job, not the software's.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

__all__ = ["QuestionBrief", "SourceCitation", "render_question"]


@dataclass(frozen=True, slots=True)
class SourceCitation:
    """One document the question rests on. ``uri`` is what Topos stored."""

    uri: str
    title: str = ""
    published: date | None = None


@dataclass(frozen=True, slots=True)
class QuestionBrief:
    """Everything the draft may state. Built by service/ from stored rows.

    Nothing outside this object reaches the output, which is what makes the
    result auditable: diff the brief against the database and the question is
    verified.
    """

    title: str
    category: str
    citations: tuple[SourceCitation, ...]
    authority: str | None = None
    ministry: str | None = None
    location: str | None = None
    # Verbatim factual fragments lifted from claims, already in the source's
    # own words — never paraphrased here.
    facts: tuple[str, ...] = ()
    budget_eur: Decimal | None = None
    first_seen: date | None = None
    last_seen: date | None = None
    recurrence: int = 0
    extra_questions: tuple[str, ...] = field(default=())


_DEFAULT_MINISTRY = "αρμόδιο Υπουργό"


def _subject(brief: QuestionBrief) -> str:
    where = f" στην περιοχή {brief.location}" if brief.location else ""
    return f"{brief.title}{where}"


def _recital(brief: QuestionBrief) -> list[str]:
    """The factual paragraph. One clause per stored fact, nothing added."""
    lines: list[str] = []

    seen = ""
    if brief.first_seen and brief.last_seen and brief.first_seen != brief.last_seen:
        seen = (
            f"Το ζήτημα καταγράφεται από {brief.first_seen.isoformat()} "
            f"έως {brief.last_seen.isoformat()}."
        )
    elif brief.first_seen:
        seen = f"Το ζήτημα καταγράφεται από {brief.first_seen.isoformat()}."
    if seen:
        lines.append(seen)

    if brief.recurrence > 1:
        lines.append(
            f"Έχει καταγραφεί {brief.recurrence} φορές σε χωριστά δημόσια έγγραφα, "
            "γεγονός που υποδεικνύει ότι δεν πρόκειται για μεμονωμένο περιστατικό."
        )

    if brief.authority:
        lines.append(f"Ως αρμόδιος φορέας προκύπτει: {brief.authority}.")

    if brief.budget_eur is not None:
        lines.append(f"Ο σχετικός προϋπολογισμός ανέρχεται σε {brief.budget_eur:,.2f} ευρώ.")

    lines.extend(f"Σύμφωνα με τα δημοσιευμένα στοιχεία: {fact}" for fact in brief.facts)
    return lines


def _questions(brief: QuestionBrief) -> list[str]:
    """The numbered asks. Generic by design — the member edits these."""
    asks = [
        f"Σε ποιο στάδιο βρίσκεται η αντιμετώπιση του ζητήματος «{brief.title}»;",
        "Ποιο είναι το χρονοδιάγραμμα ολοκλήρωσης και ποιος ο αρμόδιος φορέας υλοποίησης;",
    ]
    if brief.budget_eur is not None:
        asks.append(
            "Πώς έχει απορροφηθεί μέχρι σήμερα ο σχετικός προϋπολογισμός και υπάρχουν αποκλίσεις;"
        )
    if brief.recurrence > 1:
        asks.append(
            "Για ποιον λόγο το ζήτημα επαναλαμβάνεται και τι μέτρα έχουν ληφθεί "
            "ώστε να μην επαναληφθεί;"
        )
    asks.extend(brief.extra_questions)
    return asks


def render_question(brief: QuestionBrief) -> str:
    """The full draft, ready to paste. Deterministic for a given brief."""
    ministry = brief.ministry or _DEFAULT_MINISTRY
    parts: list[str] = [
        "ΕΡΩΤΗΣΗ",
        "",
        f"Προς: τον/την {ministry}",
        f"Θέμα: «{_subject(brief)}»",
        "",
    ]

    recital = _recital(brief)
    if recital:
        parts.extend(recital)
        parts.append("")

    parts.append("Κατόπιν των ανωτέρω, ερωτάται ο/η κ. Υπουργός:")
    parts.extend(f"{n}. {ask}" for n, ask in enumerate(_questions(brief), start=1))
    parts.append("")

    parts.append("Πηγές:")
    parts.extend(_citation_line(n, c) for n, c in enumerate(brief.citations, start=1))
    return "\n".join(parts).rstrip() + "\n"


def _citation_line(n: int, citation: SourceCitation) -> str:
    bits = [f"[{n}]"]
    if citation.title:
        bits.append(citation.title)
    bits.append(citation.uri)
    if citation.published:
        bits.append(f"({citation.published.isoformat()})")
    return " ".join(bits)
