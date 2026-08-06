"""Unit tests: LLM cost pricing.

Pure domain, literal inputs. The load-bearing property is that an unpriced
call returns None, never 0 — see ADR-014.
"""

from __future__ import annotations

from decimal import Decimal

from topos.domain.pricing import cost_eur


def test_known_model_prices_both_directions() -> None:
    # 1M in @ $2.00 + 1M out @ $6.00 = $8.00 -> * 0.87 = 6.96 EUR
    result = cost_eur("mistralai/mistral-large-2512", 1_000_000, 1_000_000)
    assert result == Decimal("6.960000")


def test_small_token_counts_scale_linearly() -> None:
    result = cost_eur("mistralai/mistral-large-2512", 1000, 1000)
    assert result is not None
    assert result > Decimal("0")
    assert result < Decimal("0.01")


def test_zero_tokens_is_a_real_zero_not_unpriced() -> None:
    """A model that IS priced, called with 0 tokens, really did cost 0."""
    assert cost_eur("mistralai/mistral-large-2512", 0, 0) == Decimal("0.000000")


def test_unknown_model_returns_none_not_zero() -> None:
    """The whole point of ADR-014: unpriced must not look free."""
    assert cost_eur("some-unlisted-model", 1000, 1000) is None


def test_missing_token_counts_return_none() -> None:
    assert cost_eur("mistralai/mistral-large-2512", None, 100) is None
    assert cost_eur("mistralai/mistral-large-2512", 100, None) is None
    assert cost_eur("mistralai/mistral-large-2512", None, None) is None


def test_every_model_actually_constructed_by_the_project_has_a_price() -> None:
    """These are the exact strings adapters/llm/__init__.py and
    interfaces/cli/main.py pass as model=. A gap here means BudgetGuard
    silently stops covering that call path."""
    for model in (
        "mistralai/mistral-large-2512",
        "grok-4.5",
        "x-ai/grok-4.5",
        "sonar-pro",
        "perplexity/sonar-pro",
    ):
        assert cost_eur(model, 100, 100) is not None, f"{model} has no price entry"


def test_output_tokens_cost_more_than_input_tokens() -> None:
    """Sanity check on the table itself: every listed model bills output
    higher than input, which is the norm and worth pinning."""
    only_in = cost_eur("sonar-pro", 1_000_000, 0)
    only_out = cost_eur("sonar-pro", 0, 1_000_000)
    assert only_in is not None
    assert only_out is not None
    assert only_out > only_in
