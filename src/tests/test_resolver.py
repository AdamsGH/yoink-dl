"""Tests for URL resolver - engine selection, proxy routing."""
from __future__ import annotations

import pytest

from yoink_dl.url.domains import DomainConfig, domain_matches, extract_domain
from yoink_dl.url.resolver import Engine, resolve


@pytest.fixture
def domain_cfg():
    return DomainConfig()


class TestExtractDomain:
    def test_basic(self):
        assert extract_domain("https://www.youtube.com/watch?v=abc") == "youtube.com"

    def test_subdomain(self):
        assert extract_domain("https://music.youtube.com/watch?v=abc") == "music.youtube.com"

    def test_no_www(self):
        assert extract_domain("https://example.com/path") == "example.com"

    def test_invalid(self):
        assert extract_domain("not-a-url") == ""

    def test_empty(self):
        assert extract_domain("") == ""


class TestDomainMatches:
    def test_exact(self):
        assert domain_matches("youtube.com", ["youtube.com"])

    def test_subdomain(self):
        assert domain_matches("music.youtube.com", ["youtube.com"])

    def test_no_match(self):
        assert not domain_matches("example.com", ["youtube.com"])

    def test_partial_no_match(self):
        assert not domain_matches("notyoutube.com", ["youtube.com"])

    def test_empty_list(self):
        assert not domain_matches("youtube.com", [])


class TestResolveEngine:
    def test_youtube_uses_ytdlp(self, domain_cfg):
        r = resolve("https://www.youtube.com/watch?v=abc", domain_cfg)
        assert r.engine == Engine.YTDLP
        assert r.domain == "youtube.com"

    def test_youtu_be_uses_ytdlp(self, domain_cfg):
        r = resolve("https://youtu.be/abc", domain_cfg)
        assert r.engine == Engine.YTDLP

    def test_gallery_only_domain(self, domain_cfg):
        r = resolve("https://gelbooru.com/post/123", domain_cfg)
        assert r.engine == Engine.GALLERY_DL

    def test_instagram_uses_fallback(self, domain_cfg):
        r = resolve("https://www.instagram.com/p/abc123/", domain_cfg)
        assert r.engine == Engine.YTDLP_THEN_GALLERY

    def test_unknown_domain_defaults_ytdlp(self, domain_cfg):
        r = resolve("https://random-site.net/video", domain_cfg)
        assert r.engine == Engine.YTDLP


class TestResolveProxy:
    def test_no_proxy_by_default(self, domain_cfg):
        r = resolve("https://youtube.com/watch?v=abc", domain_cfg)
        assert r.use_proxy == 0

    def test_proxy_domain(self):
        cfg = DomainConfig(proxy_domains=["blocked.site"])
        r = resolve("https://blocked.site/video", cfg)
        assert r.use_proxy == 1

    def test_proxy_2_domain(self):
        cfg = DomainConfig(proxy_2_domains=["other.site"])
        r = resolve("https://other.site/video", cfg)
        assert r.use_proxy == 2

    def test_user_proxy(self, domain_cfg):
        r = resolve("https://example.com/vid", domain_cfg, proxy_enabled=True)
        assert r.use_proxy == 1

    def test_custom_proxy_url(self, domain_cfg):
        r = resolve(
            "https://example.com/vid", domain_cfg,
            custom_proxy_url="socks5://1.2.3.4:1080",
        )
        assert r.custom_proxy_url == "socks5://1.2.3.4:1080"


class TestResolveCookies:
    def test_cookies_by_default(self, domain_cfg):
        r = resolve("https://youtube.com/watch?v=abc", domain_cfg)
        assert r.use_cookies is True

    def test_no_cookie_domain(self, domain_cfg):
        r = resolve("https://dailymotion.com/video/abc", domain_cfg)
        assert r.use_cookies is False


class TestResolvePlaylist:
    def test_playlist_range(self, domain_cfg):
        r = resolve(
            "https://youtube.com/playlist?list=PL123", domain_cfg,
            playlist_start=1, playlist_end=5,
        )
        assert r.is_playlist is True
        assert r.playlist_start == 1
        assert r.playlist_end == 5

    def test_no_playlist(self, domain_cfg):
        r = resolve("https://youtube.com/watch?v=abc", domain_cfg)
        assert r.is_playlist is False
