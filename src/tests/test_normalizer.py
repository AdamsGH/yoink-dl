"""Tests for URL normalization."""
from __future__ import annotations

import pytest

from yoink_dl.url.normalizer import (
    extract_range,
    is_playlist_url,
    normalize,
    normalize_for_cache,
)
from yoink_dl.url.domains import DomainConfig


@pytest.fixture
def domain_cfg():
    return DomainConfig()


class TestNormalize:
    def test_strips_tracking_params(self, domain_cfg):
        url = "https://example.com/video?v=123&utm_source=twitter&fbclid=abc"
        result = normalize(url, domain_cfg)
        assert "utm_source" not in result
        assert "fbclid" not in result
        assert "v=123" in result

    def test_resolves_google_redirect(self, domain_cfg):
        url = "https://www.google.com/url?q=https://youtube.com/watch?v=abc"
        result = normalize(url, domain_cfg)
        assert result.startswith("https://youtube.com")
        assert "v=abc" in result

    def test_strips_range_tags(self, domain_cfg):
        url = "https://youtube.com/playlist*1*5"
        result = normalize(url, domain_cfg)
        assert "*1*5" not in result
        assert result == "https://youtube.com/playlist"

    def test_empty_url(self, domain_cfg):
        assert normalize("", domain_cfg) == ""
        assert normalize(None, domain_cfg) == ""

    def test_preserves_essential_params(self, domain_cfg):
        url = "https://youtube.com/watch?v=dQw4w9WgXcQ&list=PLrAXtmEr"
        result = normalize(url, domain_cfg)
        assert "v=dQw4w9WgXcQ" in result
        assert "list=PLrAXtmEr" in result

    def test_pornhub_keeps_full_url(self):
        cfg = DomainConfig()
        url = "https://www.pornhub.com/view_video.php?viewkey=abc123"
        result = normalize(url, cfg)
        assert "viewkey=abc123" in result
        assert result.startswith("https://pornhub.com")


class TestNormalizeForCache:
    def test_youtube_watch_keeps_only_v(self):
        url = "https://www.youtube.com/watch?v=abc&list=PLxx&index=3&si=xyz"
        result = normalize_for_cache(url)
        assert result == "https://www.youtube.com/watch?v=abc"

    def test_youtube_playlist_keeps_only_list(self):
        url = "https://www.youtube.com/playlist?list=PLxyz&si=abc"
        result = normalize_for_cache(url)
        assert result == "https://www.youtube.com/playlist?list=PLxyz"

    def test_youtube_shorts_strips_params(self):
        url = "https://www.youtube.com/shorts/abc123?si=xyz"
        result = normalize_for_cache(url)
        assert result == "https://www.youtube.com/shorts/abc123"

    def test_youtu_be_strips_params(self):
        url = "https://youtu.be/abc123?si=xyz&t=10"
        result = normalize_for_cache(url)
        assert result == "https://youtu.be/abc123"

    def test_tiktok_strips_params(self):
        url = "https://www.tiktok.com/@user/video/123?is_from_webapp=1"
        result = normalize_for_cache(url)
        assert result == "https://www.tiktok.com/@user/video/123"

    def test_clean_query_domains(self):
        cfg = DomainConfig()
        url = "https://x.com/user/status/123?s=20&t=abc"
        result = normalize_for_cache(url, cfg)
        assert result == "https://x.com/user/status/123"


class TestExtractRange:
    def test_positive_range(self):
        url, start, end = extract_range("https://example.com/playlist*1*5")
        assert url == "https://example.com/playlist"
        assert start == 1
        assert end == 5

    def test_negative_range(self):
        url, start, end = extract_range("https://example.com/vid*-1*-5")
        assert url == "https://example.com/vid"
        assert start == -1
        assert end == -5

    def test_no_range(self):
        url, start, end = extract_range("https://example.com/video")
        assert url == "https://example.com/video"
        assert start is None
        assert end is None


class TestIsPlaylistUrl:
    def test_with_range(self):
        assert is_playlist_url("https://x.com/playlist*1*10")

    def test_without_range(self):
        assert not is_playlist_url("https://x.com/video")

    def test_negative_range(self):
        assert is_playlist_url("https://x.com/list*-1*-3")
