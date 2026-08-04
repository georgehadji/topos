# ruff: noqa: RUF001
"""Unit tests: shared civic-feed parsing.

Pure parsing, literal inputs — no network. The fixtures mirror the real
response shapes probed on 2026-08-04.
"""

from __future__ import annotations

from topos.adapters.sources.feedbase import _rss_items, _wp_items, strip_html


def test_strip_html_removes_tags_and_decodes_entities() -> None:
    out = strip_html("<p>Διακοπή &amp; βλάβη</p>")
    assert out == "Διακοπή & βλάβη"


def test_strip_html_drops_script_and_style_bodies() -> None:
    """thestival.gr leaked JS boilerplate into extraction as a fake 'problem'."""
    out = strip_html("<style>.a{color:red}</style><script>var x=1;</script><p>κείμενο</p>")
    assert "color" not in out
    assert "var x" not in out
    assert out == "κείμενο"


def test_wp_items_reads_rendered_subfields() -> None:
    body = (
        '[{"slug":"anakoinosi-1","title":{"rendered":"Διακοπή νερού"},'
        '"content":{"rendered":"<p>Στη Σταυρούπολη</p>"}}]'
    )
    items = _wp_items(body, 10)
    assert items == [("anakoinosi-1", "Διακοπή νερού", "Διακοπή νερού. Στη Σταυρούπολη")]


def test_wp_items_falls_back_to_excerpt_when_content_is_empty() -> None:
    body = (
        '[{"slug":"x","title":{"rendered":"Τίτλος"},"content":{"rendered":""},'
        '"excerpt":{"rendered":"περίληψη"}}]'
    )
    assert _wp_items(body, 10)[0][2] == "Τίτλος. περίληψη"


def test_wp_items_returns_empty_for_non_json() -> None:
    """An RSS body must fall through to the RSS parser, not raise."""
    assert _wp_items("<rss><channel></channel></rss>", 10) == []


def test_wp_items_returns_empty_for_json_that_is_not_a_post_array() -> None:
    assert _wp_items('{"code":"rest_no_route"}', 10) == []


def test_rss_items_extracts_title_link_and_description() -> None:
    body = (
        "<rss><channel><item>"
        "<title>Έργα οδοποιίας</title>"
        "<link>https://example.gr/erga-odopoiias/</link>"
        "<description>Ξεκινούν εργασίες</description>"
        "</item></channel></rss>"
    )
    items = _rss_items(body, 10)
    assert items == [("erga-odopoiias", "Έργα οδοποιίας", "Έργα οδοποιίας. Ξεκινούν εργασίες")]


def test_rss_items_handles_cdata() -> None:
    body = (
        "<item><title><![CDATA[Διακοπή]]></title>"
        "<link>https://x.gr/a</link>"
        "<description><![CDATA[<p>κείμενο</p>]]></description></item>"
    )
    assert _rss_items(body, 10)[0][2] == "Διακοπή. κείμενο"


def test_rss_items_prefers_content_encoded_over_nothing() -> None:
    body = (
        "<item><title>Τ</title><link>https://x.gr/b</link>"
        "<content:encoded>πλήρες κείμενο</content:encoded></item>"
    )
    assert "πλήρες κείμενο" in _rss_items(body, 10)[0][2]


def test_rss_items_respects_the_limit() -> None:
    body = "".join(
        f"<item><title>T{i}</title><link>https://x.gr/{i}</link>"
        f"<description>d{i}</description></item>"
        for i in range(10)
    )
    assert len(_rss_items(body, 3)) == 3


def test_empty_feed_yields_no_items() -> None:
    """oasth.gr serves a valid RSS document with zero items."""
    body = "<rss version='2.0'><channel><title>ΟΑΣΘ</title></channel></rss>"
    assert _rss_items(body, 10) == []
    assert _wp_items(body, 10) == []
