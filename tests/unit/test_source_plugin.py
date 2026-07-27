"""Unit tests: source plugin registry."""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from topos.adapters.sources.base import SourcePlugin
from topos.adapters.sources.deddhe import DeddheConfig, DeddhePlugin
from topos.adapters.sources.fek import FekConfig, FekPlugin
from topos.adapters.sources.registry import get, list_kinds, register


class DummyPluginConfig(BaseModel):
    url: str = ""


class GoodPlugin(SourcePlugin):
    kind = "test_good"
    config_model = DummyPluginConfig


@register
class DecoratedPlugin(SourcePlugin):
    kind = "test_decorated"
    config_model = DummyPluginConfig


def test_register_and_get() -> None:
    register(GoodPlugin)
    assert get("test_good") is GoodPlugin


def test_register_returns_the_class() -> None:
    assert get("test_decorated") is DecoratedPlugin


def test_get_unknown() -> None:
    assert get("nonexistent") is None


def test_list_kinds_includes_registered() -> None:
    kinds = list_kinds()
    assert "test_good" in kinds
    assert "test_decorated" in kinds


def test_list_kinds_is_sorted() -> None:
    kinds = list_kinds()
    assert kinds == sorted(kinds)


@pytest.mark.asyncio
async def test_fek_plugin_fetch() -> None:
    plugin = FekPlugin()
    assert plugin.kind == "fek"
    assert plugin.config_model is FekConfig

    config = FekConfig(max_items=1)
    artifacts = []
    async for art in plugin.fetch(config):
        artifacts.append(art)

    assert len(artifacts) == 1
    assert artifacts[0].uri.startswith("fek://")
    assert (
        b"Toump" in artifacts[0].data
        or b"\xce\xa4\xce\xbf\xcf\x8d\xce\xbc\xcf\x80" in artifacts[0].data
    )


@pytest.mark.asyncio
async def test_deddhe_plugin_fetch() -> None:
    plugin = DeddhePlugin()
    assert plugin.kind == "deddhe"
    assert plugin.config_model is DeddheConfig

    config = DeddheConfig(max_items=1)
    artifacts = []
    async for art in plugin.fetch(config):
        artifacts.append(art)

    assert len(artifacts) == 1
    assert artifacts[0].uri.startswith("deddhe://")
