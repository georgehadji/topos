"""Unit tests: OpenRouterProvider's pure content-builder (Phase 6 #6.4, ADR-019)."""

from __future__ import annotations

from topos.adapters.llm.provider import _content_for


def test_no_prefix_returns_the_plain_prompt_string() -> None:
    """Unchanged behaviour for every caller that does not pass cache_prefix."""
    assert _content_for("hello", None) == "hello"


def test_empty_prefix_is_treated_as_no_prefix() -> None:
    assert _content_for("hello", "") == "hello"


def test_prefix_produces_a_cache_marked_content_array() -> None:
    content = _content_for("chunk text", "static preamble")
    assert content == [
        {"type": "text", "text": "static preamble", "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": "chunk text"},
    ]


def test_parts_concatenate_to_the_original_prompt() -> None:
    """A provider that ignores cache_control must still see the same text a
    single-string prompt would have carried."""
    preamble, prompt = "static preamble\n\n", "Document excerpt:\n---\nbody\n---"
    content = _content_for(prompt, preamble)
    assert isinstance(content, list)
    assert "".join(part["text"] for part in content) == preamble + prompt
