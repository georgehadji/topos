"""Per-model LLM pricing — a versioned policy table, not a computation.

``Telemetry._record`` inserted a literal ``0`` for every ``cost_eur``, which
meant ``topos-cli cost`` has always reported EUR0 and ``BudgetGuard``'s
monthly ceiling — computed as ``SUM(cost_eur)`` — has never been able to fire.
``tokens_in``/``tokens_out`` were already recorded; price was the only
missing input.

Rates are the vendor's own published USD price per 1M tokens, same shape as
``domain/severity.py``: an explicit table someone edits deliberately, not a
formula. Converted to EUR at a fixed documented rate rather than a live FX
call — this project does not have a rates adapter, and a wrong-by-a-few-percent
budget figure is a acceptable, an unmeasured one is not.

An unpriced (unknown) model returns ``None``, never ``0``. Zero would say
"this call was free", which is a stronger and false claim — the same
fabricate-a-plausible-number failure class as the ΔΕΔΔΗΕ sample fallback.
"""

from __future__ import annotations

from decimal import Decimal

__all__ = ["PRICING_VER", "cost_eur"]

PRICING_VER = "1.0.0"

# USD per Federal Reserve H.10, captured 2026-08-05. Update alongside the
# price table below when either changes materially — both drift, neither
# drifts often enough to justify a live lookup for a EUR250/month budget.
_USD_EUR_RATE = Decimal("0.87")

# (input $/1M tokens, output $/1M tokens). Sourced from each vendor's public
# pricing page, captured 2026-08-05. Keys are the exact strings this project
# passes as LlmClient.complete(model=...) — see adapters/llm/__init__.py and
# interfaces/cli/main.py for where each is constructed. Deliberately listed
# per spelling rather than normalised: a normaliser that guesses wrong is a
# silent mispricing, where a missing entry is a loud, visible None.
_USD_PER_MILLION: dict[str, tuple[Decimal, Decimal]] = {
    "mistralai/mistral-large-2512": (Decimal("2.00"), Decimal("6.00")),
    "mistralai/mistral-large": (Decimal("2.00"), Decimal("6.00")),
    # Grok 4.5's <=200K-token tier. This project's chunks are single-document
    # excerpts, never remotely close to 200K, so the >200K tier ($4/$12) is
    # deliberately not modelled — add it if handle_textified ever real-chunks
    # a document large enough to reach it (see PHASE6_TOKEN_PLAN.md #6.7).
    "grok-4.5": (Decimal("2.00"), Decimal("6.00")),
    "x-ai/grok-4.5": (Decimal("2.00"), Decimal("6.00")),
    # Sonar's per-request web-search surcharge ($6-14/1000 requests) is not
    # token-denominated and Telemetry only has token counts, so it is not
    # included here. cost_eur for sonar calls is therefore a floor, not the
    # full bill — noted, not silently absorbed into the token rate.
    "sonar-pro": (Decimal("3.00"), Decimal("15.00")),
    "perplexity/sonar-pro": (Decimal("3.00"), Decimal("15.00")),
}


def cost_eur(model: str, tokens_in: int | None, tokens_out: int | None) -> Decimal | None:
    """EUR cost of one call, or None when the model has no price entry.

    None (not zero) on: unknown model, or missing token counts — a call this
    function cannot price must not be reported as a free one.
    """
    if tokens_in is None or tokens_out is None:
        return None
    rates = _USD_PER_MILLION.get(model)
    if rates is None:
        return None

    in_rate, out_rate = rates
    million = Decimal(1_000_000)
    usd = (Decimal(tokens_in) / million * in_rate) + (Decimal(tokens_out) / million * out_rate)
    return (usd * _USD_EUR_RATE).quantize(Decimal("0.000001"))
