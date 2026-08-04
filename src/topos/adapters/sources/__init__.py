"""Source plugin registry. See ARCHITECTURE.md and slice 0.11.

Importing these submodules here ensures that every source plugin is imported
and automatically registered via the `@register` decorator when the package is
loaded. A plugin missing from this list is invisible to `topos-cli sources`
and to `backfill --source` however correct its own code is.
"""

from __future__ import annotations

from topos.adapters.sources import (
    civic,
    data_gov,
    deddhe,
    diavgeia,
    fek,
    hazards,
    khmdhs,
    municipality,
    news,
    social,
    sonar_web,
    transport,
    websearch,
)

__all__ = [
    "civic",
    "data_gov",
    "deddhe",
    "diavgeia",
    "fek",
    "hazards",
    "khmdhs",
    "municipality",
    "news",
    "social",
    "sonar_web",
    "transport",
    "websearch",
]
