"""Source plugin registry.

Plugins register by ``kind``. The stepper looks up a source's ``kind``
to find the right plugin for fetching and parsing.
"""

from __future__ import annotations

from topos.adapters.sources.base import SourcePlugin

_registry: dict[str, type[SourcePlugin]] = {}


def register(plugin: type[SourcePlugin]) -> type[SourcePlugin]:
    """Register a SourcePlugin subclass under its ``kind``.

    Can be used as a decorator::

        @register
        class DiavgeiaPlugin(SourcePlugin):
            kind = "diavgeia"
            ...
    """
    _registry[plugin.kind] = plugin
    return plugin


def get(kind: str) -> type[SourcePlugin] | None:
    """Look up a plugin by its ``kind`` string. Returns None if unknown."""
    return _registry.get(kind)


def list_kinds() -> list[str]:
    """Return all registered plugin kinds."""
    return list(_registry.keys())
