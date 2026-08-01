"""Source plugin registry. See ARCHITECTURE.md and slice 0.11.

Importing these submodules here ensures that all source plugins (diavgeia,
khmdhs, municipality, news, fek, deddhe, sonar_web, social) are imported and
automatically registered via the `@register` decorator when the package is
loaded.
"""

from __future__ import annotations

from topos.adapters.sources import (
    deddhe,
    diavgeia,
    fek,
    khmdhs,
    municipality,
    news,
    social,
    sonar_web,
    websearch,
)

__all__ = [
    "deddhe",
    "diavgeia",
    "fek",
    "khmdhs",
    "municipality",
    "news",
    "social",
    "sonar_web",
    "websearch",
]
