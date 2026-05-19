"""Tests for caption builder."""
from __future__ import annotations

from unittest.mock import MagicMock

from yoink_dl.upload.caption import build_caption, build_group_caption


def _settings(**overrides):
    s = MagicMock()
    s.MANAGED_BY = overrides.get("managed_by", "")
    s.CREDITS_BOTS = overrides.get("credits_bots", "")
    return s


class TestBuildCaption:
    def test_basic(self):
        caption = build_caption(
            title="My Video", url="https://example.com/vid", settings=_settings()
        )
        # Title is wrapped in the source link, not a separate "source" line.
        assert '<a href="https://example.com/vid"><b>My Video</b></a>' in caption
        assert "source" not in caption

    def test_html_escaping(self):
        caption = build_caption(
            title="<script>alert(1)</script>",
            url="https://example.com", settings=_settings(),
        )
        assert "&lt;script&gt;" in caption
        assert "<script>" not in caption

    def test_extra_field(self):
        caption = build_caption(
            title="Test", url="https://example.com",
            settings=_settings(), extra="clip info",
        )
        assert "clip info" in caption

    def test_truncation(self):
        long_title = "A" * 2000
        caption = build_caption(
            title=long_title, url="https://example.com", settings=_settings(),
        )
        assert len(caption) <= 1024

    def test_empty_title(self):
        caption = build_caption(
            title="", url="https://example.com", settings=_settings(),
        )
        # Without a title we fall back to a plain "source" link.
        assert '<a href="https://example.com">source</a>' in caption


class TestBuildGroupCaption:
    def test_contains_mention(self):
        caption = build_group_caption(
            url="https://example.com/vid",
            requester_name="TestUser",
            requester_id=12345,
        )
        assert 'tg://user?id=12345' in caption
        assert "TestUser" in caption
        assert "source" in caption

    def test_html_escaping_name(self):
        caption = build_group_caption(
            url="https://example.com",
            requester_name="User<br>",
            requester_id=1,
        )
        assert "User&lt;br&gt;" in caption
        assert "<br>" not in caption
