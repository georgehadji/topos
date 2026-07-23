"""Source plugin base class and contract.

Each source type (Διαύγεια, ΚΗΜΔΗΣ, ΦΕΚ, etc.) implements a SourcePlugin
subclass and registers it with the SourceRegistry (registry.py).

The contract:
  - ``kind`` — short text identifier, e.g. ``"diavgeia"``
  - ``config_model`` — Pydantic model for the source's config.jsonb
  - ``fetch()`` — called by the pipeline's FETCHED handler; yields artifacts
  - ``parse()`` — called by the pipeline's TEXTIFIED handler; returns text + claims

See ARCHITECTURE.md > Repository layout and > The pipeline.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, ClassVar

from pydantic import BaseModel


@dataclass(frozen=True, slots=True)
class PluginArtifact:
    """One artifact produced by a source plugin.

    The plugin fetches raw data and yields these. The stepper persists
    them via the artifact/blob/pipeline repositories.
    """

    uri: str
    data: bytes
    mime: str
    meta: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class PluginEntry:
    """One chunk and its extracted claims from a parsed document."""

    text: str
    claims: list[dict[str, Any]] | None = None


class SourcePlugin:
    """Base class for all source plugins.

    Subclasses override ``kind``, ``config_model``, ``fetch()`` and
    ``parse()``.
    """

    kind: ClassVar[str]
    config_model: ClassVar[type[BaseModel]]

    async def fetch(
        self, config: BaseModel
    ) -> AsyncIterator[PluginArtifact]:
        """Fetch new artifacts from the source.

        *config* is the parsed config.jsonb validated against
        ``config_model``.
        """
        # Default: no-op. Subclasses override and yield.
        return
        yield  # type: ignore[unreachable]

    async def parse(
        self, data: bytes, mime: str
    ) -> AsyncIterator[PluginEntry]:
        """Parse a downloaded artifact into text and optional claims."""
        # Default: no-op. Subclasses override and yield.
        return
        yield  # type: ignore[unreachable]
