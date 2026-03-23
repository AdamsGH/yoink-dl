"""Tests for download log repository."""
from __future__ import annotations

import pytest

from yoink.core.db.models import User
from yoink_dl.storage.repos import DownloadLogRepo


USER_ID = 200010


@pytest.fixture
async def user(session_factory):
    async with session_factory() as sess:
        existing = await sess.get(User, USER_ID)
        if not existing:
            sess.add(User(id=USER_ID, username="dl_log_test", first_name="DL"))
            await sess.commit()
    yield
    async with session_factory() as sess:
        u = await sess.get(User, USER_ID)
        if u:
            await sess.delete(u)
            await sess.commit()


class TestDownloadLog:
    async def test_write_and_list(self, session_factory, user):
        dl_log = DownloadLogRepo(session_factory)
        await dl_log.write(
            USER_ID, "https://youtube.com/watch?v=abc",
            title="Test Video", quality="best",
            file_size=5_000_000, duration=120.5,
            status="ok",
        )
        entries, total = await dl_log.list_for_user(USER_ID)
        assert total >= 1
        latest = entries[0]
        assert latest.url == "https://youtube.com/watch?v=abc"
        assert latest.title == "Test Video"
        assert latest.domain == "youtube.com"
        assert latest.status == "ok"

    async def test_write_error(self, session_factory, user):
        dl_log = DownloadLogRepo(session_factory)
        await dl_log.write(
            USER_ID, "https://broken.com/video",
            status="error", error_msg="Download failed",
        )
        entries, _ = await dl_log.list_for_user(USER_ID)
        error_entry = next(e for e in entries if e.url == "https://broken.com/video")
        assert error_entry.status == "error"
        assert error_entry.error_msg == "Download failed"

    async def test_auto_creates_user(self, session_factory):
        new_user_id = 200099
        dl_log = DownloadLogRepo(session_factory)
        await dl_log.write(new_user_id, "https://example.com/vid", status="ok")
        entries, total = await dl_log.list_for_user(new_user_id)
        assert total >= 1
        async with session_factory() as sess:
            u = await sess.get(User, new_user_id)
            if u:
                await sess.delete(u)
                await sess.commit()

    async def test_pagination(self, session_factory, user):
        dl_log = DownloadLogRepo(session_factory)
        for i in range(5):
            await dl_log.write(
                USER_ID, f"https://example.com/vid{i}", status="ok",
            )
        entries, total = await dl_log.list_for_user(USER_ID, offset=0, limit=2)
        assert len(entries) == 2
        assert total >= 5

    async def test_update(self, session_factory, user):
        dl_log = DownloadLogRepo(session_factory)
        await dl_log.write(USER_ID, "https://example.com/update_test", status="ok")
        entries, _ = await dl_log.list_for_user(USER_ID)
        target = next(e for e in entries if e.url == "https://example.com/update_test")
        updated = await dl_log.update(target.id, status="cached")
        assert updated is not None
        assert updated.status == "cached"
