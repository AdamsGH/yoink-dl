"""Tests for rate limiter repository."""
from __future__ import annotations

import pytest

from yoink.core.db.models import User
from yoink_dl.storage.repos import RateLimitRepo


USER_ID = 200001


@pytest.fixture
async def user(session_factory):
    async with session_factory() as sess:
        existing = await sess.get(User, USER_ID)
        if not existing:
            sess.add(User(id=USER_ID, username="ratelimit_test", first_name="RL"))
            await sess.commit()
    yield
    async with session_factory() as sess:
        u = await sess.get(User, USER_ID)
        if u:
            await sess.delete(u)
            await sess.commit()


class TestRateLimiter:
    async def test_allowed_within_limits(self, session_factory, user):
        rl = RateLimitRepo(session_factory)
        allowed, reason = await rl.check_and_increment(
            user_id=USER_ID, limit_minute=5, limit_hour=30, limit_day=100,
        )
        assert allowed is True
        assert reason == ""

    async def test_minute_limit_exceeded(self, session_factory, user):
        rl = RateLimitRepo(session_factory)
        for _ in range(3):
            await rl.check_and_increment(
                user_id=USER_ID, limit_minute=3, limit_hour=100, limit_day=100,
            )
        allowed, reason = await rl.check_and_increment(
            user_id=USER_ID, limit_minute=3, limit_hour=100, limit_day=100,
        )
        assert allowed is False
        assert reason == "minute"

    async def test_hour_limit_exceeded(self, session_factory, user):
        rl = RateLimitRepo(session_factory)
        for _ in range(2):
            await rl.check_and_increment(
                user_id=USER_ID, limit_minute=100, limit_hour=2, limit_day=100,
            )
        allowed, reason = await rl.check_and_increment(
            user_id=USER_ID, limit_minute=100, limit_hour=2, limit_day=100,
        )
        assert allowed is False
        assert reason == "hour"

    async def test_independent_users(self, session_factory, user):
        other_id = 200002
        async with session_factory() as sess:
            if not await sess.get(User, other_id):
                sess.add(User(id=other_id, username="other", first_name="Other"))
                await sess.commit()
        rl = RateLimitRepo(session_factory)
        for _ in range(3):
            await rl.check_and_increment(
                user_id=USER_ID, limit_minute=3, limit_hour=100, limit_day=100,
            )
        allowed, _ = await rl.check_and_increment(
            user_id=other_id, limit_minute=3, limit_hour=100, limit_day=100,
        )
        assert allowed is True
        async with session_factory() as sess:
            u = await sess.get(User, other_id)
            if u:
                await sess.delete(u)
                await sess.commit()
