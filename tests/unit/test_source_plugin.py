"""Unit tests: source plugin registry.
"""

from __future__ import annotations

from pydantic import BaseModel

from topos.adapters.sources.base import SourcePlugin
from topos.adapters.sources.registry import get, list_kinds, register


class TestConfig(BaseModel):
    url: str = ""


class GoodPlugin(SourcePlugin):
    kind = "test_good"
    config_model = TestConfig


@register
class DecoratedPlugin(SourcePlugin):
    kind = "test_decorated"
    config_model = TestConfig


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
