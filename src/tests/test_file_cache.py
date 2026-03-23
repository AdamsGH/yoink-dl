"""Tests for file cache repository."""
from __future__ import annotations

import pytest

from yoink_dl.storage.repos import FileCacheRepo, make_cache_key


class TestMakeCacheKey:
    def test_basic_url(self):
        key = make_cache_key("https://youtube.com/watch?v=abc")
        assert key is not None
        assert len(key) == 64

    def test_same_url_same_key(self):
        k1 = make_cache_key("https://youtube.com/watch?v=abc")
        k2 = make_cache_key("https://youtube.com/watch?v=abc")
        assert k1 == k2

    def test_different_urls_different_keys(self):
        k1 = make_cache_key("https://youtube.com/watch?v=abc")
        k2 = make_cache_key("https://youtube.com/watch?v=xyz")
        assert k1 != k2

    def test_clip_changes_key(self):
        k1 = make_cache_key("https://youtube.com/watch?v=abc")
        k2 = make_cache_key("https://youtube.com/watch?v=abc", start_sec=10, end_sec=60)
        assert k1 != k2

    def test_deterministic(self):
        key = make_cache_key("")
        assert isinstance(key, str)
        assert len(key) == 64

    def test_audio_only_changes_key(self):
        k_video = make_cache_key("https://youtube.com/watch?v=abc")
        k_audio = make_cache_key("https://youtube.com/watch?v=abc", audio_only=True)
        assert k_video != k_audio

    def test_audio_only_same_url_same_key(self):
        k1 = make_cache_key("https://youtube.com/watch?v=abc", audio_only=True)
        k2 = make_cache_key("https://youtube.com/watch?v=abc", audio_only=True)
        assert k1 == k2


class TestFileCacheRepo:
    async def test_put_and_get(self, session_factory):
        cache = FileCacheRepo(session_factory)
        key = make_cache_key("https://example.com/video1")
        await cache.put(
            key, file_id="AgACAgIAAxkBAAI",
            file_type="video", title="Test Video",
            file_size=1_000_000, duration=120.0,
        )
        cached = await cache.get(key)
        assert cached is not None
        assert cached.file_id == "AgACAgIAAxkBAAI"
        assert cached.file_type == "video"
        assert cached.title == "Test Video"

    async def test_cache_miss(self, session_factory):
        cache = FileCacheRepo(session_factory)
        key = make_cache_key("https://example.com/nonexistent")
        assert await cache.get(key) is None

    async def test_delete(self, session_factory):
        cache = FileCacheRepo(session_factory)
        key = make_cache_key("https://example.com/video_delete")
        await cache.put(
            key, file_id="file123", file_type="video",
            title="Delete Me", file_size=100, duration=10.0,
        )
        deleted = await cache.delete(key)
        assert deleted is True
        assert await cache.get(key) is None

    async def test_delete_nonexistent(self, session_factory):
        cache = FileCacheRepo(session_factory)
        deleted = await cache.delete("nonexistent_key_hash_000000000000000000")
        assert deleted is False

    async def test_put_overwrites(self, session_factory):
        cache = FileCacheRepo(session_factory)
        key = make_cache_key("https://example.com/video_overwrite")
        await cache.put(key, file_id="old_id", file_type="video")
        await cache.put(key, file_id="new_id", file_type="audio")
        cached = await cache.get(key)
        assert cached is not None
        assert cached.file_id == "new_id"
        assert cached.file_type == "audio"
