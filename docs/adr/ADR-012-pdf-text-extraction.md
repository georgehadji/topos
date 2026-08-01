# ADR-012 — Extract the PDF text layer with pypdf; defer real OCR

- **Status:** Accepted
- **Date:** 2026-08-01
- **Adds dependency:** `pypdf>=5.1`

## Context

Διαύγεια and ΚΗΜΔΗΣ — the two highest-value Greek public-sector sources — serve
decisions as PDF. `adapters/ocr/` was an empty stub marked "Phase 2", so the
pipeline had no way to turn a fetched PDF into text.

What filled the gap instead: `service/handlers.handle_fetched` matched on the
artifact URI and substituted a hardcoded Greek sentence. A real 692 KB Διαύγεια
decision became 133 characters of invented text, which the extractor then mined
for "claims". Every problem in the database was synthetic, and nothing in the
schema distinguished them from real ones.

Fabricated evidence is worse than no evidence in a system whose entire premise is
byte-range traceability to a source document.

## Decision

Add `pypdf` and extract the PDF **text layer** in `adapters/ocr.extract_text()`.

`pypdf` is pure Python, dependency-free, MIT, and widely used. It reads the text
layer only — it does no image OCR.

When a PDF has no text layer (a scan), `extract_text()` returns `None` and the
artifact is **parked** with `no_text_layer`. It is not guessed at, and not
silently dropped.

Also handled without any dependency: `text/*` (decode), `application/json`
(recursively collect string values), `text/html` (tag strip). Those cover
ΔΕΔΔΗΕ, ΦΕΚ, news, municipality, and every search-derived source.

## Alternatives considered

**Tesseract / `pytesseract`.** Rejected for now: needs a system binary in the
image, Greek language data, and is an order of magnitude slower. It is the right
answer for scanned PDFs, and `parked/no_text_layer` is the queue that will feed
it. Deferred to the Phase 2 OCR slice rather than bundled into this change.

**`pdfplumber` / `PyMuPDF`.** `pdfplumber` pulls in `pdfminer.six`; PyMuPDF is
AGPL-or-commercial, which is a poor fit for a commercial project. `pypdf` is the
smaller, safer default and can be swapped behind `extract_text()`.

**Keep the simulated text.** Rejected. See Context.

## Consequences

- Διαύγεια/ΚΗΜΔΗΣ text is now genuine, so extraction, spans, and geocoding are
  finally operating on real documents.
- Scanned PDFs park instead of producing rows. Expect a visible `parked` count —
  that number is a real measurement of OCR debt, previously hidden behind
  fabricated text.
- Greek text quality from the PDF layer is unmeasured. AGENTS.md requires golden
  fixtures for Greek behaviour; `tests/golden/` is still empty. Treat extracted
  Greek as `[UNVERIFIED]` until those exist.
