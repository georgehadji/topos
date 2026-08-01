"""Turn fetched artifact bytes into text.

Named `ocr` because that is the slot ARCHITECTURE.md reserves for it, but no
image OCR happens here yet: PDFs are read via their **text layer** only. A
scanned PDF has no text layer, so `extract_text` returns None and the caller
parks the artifact rather than inventing content. See docs/adr/ADR-012.

Everything else is stdlib: text/* decode, JSON string harvest, HTML tag strip.
"""

from __future__ import annotations

import html
import io
import json
import logging
import re
from typing import Any

from pypdf import PdfReader

logger = logging.getLogger(__name__)

# Deepest JSON nesting worth walking; guards against pathological documents.
_MAX_JSON_DEPTH = 12

_SCRIPT_STYLE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"[ \t\r\f\v]+")
_BLANK_LINES = re.compile(r"\n{3,}")

# Below this, a "text layer" is almost certainly page furniture, not content.
_MIN_PDF_CHARS = 40


def extract_text(data: bytes, mime: str) -> str | None:
    """Best-effort text for *data*. None means "cannot read this — park it".

    None is a deliberate signal, not a failure to be papered over: the caller
    must not substitute placeholder text (ADR-012).
    """
    if not data:
        return None

    kind = (mime or "").split(";", 1)[0].strip().lower()

    if kind == "application/pdf" or data[:5] == b"%PDF-":
        return _from_pdf(data)
    if kind in ("application/json", "application/ld+json") or kind.endswith("+json"):
        return _from_json(data)
    if kind in ("text/html", "application/xhtml+xml", "text/xml", "application/xml"):
        return _clean(_from_html(data))
    if kind.startswith("text/") or not kind:
        return _clean(data.decode("utf-8", errors="replace"))

    # Unknown binary: try UTF-8, and only accept it if it looks like text.
    decoded = data.decode("utf-8", errors="ignore")
    return _clean(decoded) if len(decoded) >= _MIN_PDF_CHARS else None


def _from_pdf(data: bytes) -> str | None:
    try:
        reader = PdfReader(io.BytesIO(data))
        pages = [page.extract_text() or "" for page in reader.pages]
    except Exception:
        logger.exception("pdf parse failed")
        return None

    text = _clean("\n".join(pages))
    if len(text) < _MIN_PDF_CHARS:
        # Almost certainly a scan. Phase 2 OCR picks these up from `parked`.
        return None
    return text


def _from_json(data: bytes) -> str | None:
    try:
        parsed = json.loads(data.decode("utf-8", errors="replace"))
    except (ValueError, UnicodeDecodeError):
        logger.warning("json parse failed; falling back to raw decode")
        return _clean(data.decode("utf-8", errors="replace"))

    parts: list[str] = []
    _harvest(parsed, parts)
    return _clean("\n".join(parts))


def _harvest(node: Any, out: list[str], depth: int = 0) -> None:
    """Collect every string value, deepest-first, preserving document order."""
    if depth > _MAX_JSON_DEPTH:
        return
    if isinstance(node, str):
        if node.strip():
            out.append(node)
    elif isinstance(node, dict):
        for value in node.values():
            _harvest(value, out, depth + 1)
    elif isinstance(node, list):
        for value in node:
            _harvest(value, out, depth + 1)


def _from_html(data: bytes) -> str:
    raw = data.decode("utf-8", errors="replace")
    raw = _SCRIPT_STYLE.sub(" ", raw)
    raw = _TAG.sub(" ", raw)
    return html.unescape(raw)


def _clean(text: str) -> str:
    """Collapse runs of spaces and blank lines, keeping paragraph structure.

    Spans are byte ranges into *this* text, so normalisation must happen once,
    here, before the document is stored.
    """
    text = _WS.sub(" ", text)
    text = "\n".join(line.strip() for line in text.splitlines())
    return _BLANK_LINES.sub("\n\n", text).strip()
