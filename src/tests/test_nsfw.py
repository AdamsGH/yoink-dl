"""Tests for NSFW checker - detection and spoiler logic."""
from __future__ import annotations

import pytest

from yoink_dl.services.nsfw import NsfwChecker


@pytest.fixture
async def checker(session_factory):
    c = NsfwChecker(session_factory)
    c._domains = frozenset(["pornhub.com", "xvideos.com"])
    c._keywords = frozenset(["hentai", "xxx"])
    c._compile()
    return c


class TestNsfwDomainDetection:
    async def test_exact_domain(self, checker):
        hit, reason = checker.check("https://pornhub.com/view_video.php?v=123")
        assert hit is True
        assert "domain:" in reason

    async def test_subdomain(self, checker):
        hit, _ = checker.check("https://www.pornhub.com/video")
        assert hit is True

    async def test_safe_domain(self, checker):
        hit, _ = checker.check("https://youtube.com/watch?v=abc")
        assert hit is False

    async def test_is_nsfw_domain_method(self, checker):
        assert checker.is_nsfw_domain("https://xvideos.com/video123") is True
        assert checker.is_nsfw_domain("https://youtube.com/vid") is False


class TestNsfwKeywordDetection:
    async def test_url_keyword(self, checker):
        hit, reason = checker.check("https://example.com/xxx-video")
        assert hit is True
        assert "url_kw:" in reason

    async def test_meta_keyword(self, checker):
        info = {"title": "Some Hentai Video", "tags": [], "categories": []}
        hit, reason = checker.check("https://safe.com/video", info=info)
        assert hit is True
        assert "meta_kw:" in reason

    async def test_no_keyword_match(self, checker):
        hit, _ = checker.check("https://example.com/normal-video")
        assert hit is False

    async def test_meta_tags(self, checker):
        info = {"title": "Normal", "tags": ["hentai"], "categories": []}
        hit, reason = checker.check("https://safe.com/video", info=info)
        assert hit is True


class TestSpoilerLogic:
    def test_nsfw_private_blur_on(self):
        assert NsfwChecker.should_apply_spoiler(
            is_nsfw_content=True, user_nsfw_blur=True, is_private_chat=True,
        ) is True

    def test_nsfw_private_blur_off(self):
        assert NsfwChecker.should_apply_spoiler(
            is_nsfw_content=True, user_nsfw_blur=False, is_private_chat=True,
        ) is False

    def test_nsfw_group_never_spoiler(self):
        assert NsfwChecker.should_apply_spoiler(
            is_nsfw_content=True, user_nsfw_blur=True, is_private_chat=False,
        ) is False

    def test_safe_content_no_spoiler(self):
        assert NsfwChecker.should_apply_spoiler(
            is_nsfw_content=False, user_nsfw_blur=True, is_private_chat=True,
        ) is False
