"""Download log and rate limit repositories."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from yoink.core.db.models import User
from yoink_dl.storage.models import DownloadLog, RateLimit

logger = logging.getLogger(__name__)


class DownloadLogRepo:
    """Records every download attempt and exposes history for API queries."""

    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._sf = session_factory

    async def write(
        self,
        user_id: int,
        url: str,
        *,
        title: str | None = None,
        quality: str | None = None,
        file_size: int | None = None,
        duration: float | None = None,
        file_count: int | None = None,
        status: str = "ok",
        error_msg: str | None = None,
        group_id: int | None = None,
        thread_id: int | None = None,
        message_id: int | None = None,
        clip_start: int | None = None,
        clip_end: int | None = None,
    ) -> None:
        """Write a log entry. Silently swallows errors."""
        domain = urlparse(url).netloc or None
        try:
            async with self._sf() as s:
                user = await s.get(User, user_id)
                if user is None:
                    user = User(id=user_id)
                    s.add(user)
                    await s.flush()
                s.add(DownloadLog(
                    user_id=user_id, url=url, domain=domain, title=title,
                    quality=quality, file_size=file_size, duration=duration,
                    file_count=file_count, status=status, error_msg=error_msg,
                    group_id=group_id, thread_id=thread_id, message_id=message_id,
                    clip_start=clip_start, clip_end=clip_end,
                ))
                await s.commit()
        except Exception as exc:
            logger.warning("Failed to write download_log: %s", exc)

    async def list_for_user(
        self, user_id: int, offset: int = 0, limit: int = 50
    ) -> tuple[list[DownloadLog], int]:
        async with self._sf() as s:
            total = (await s.execute(
                select(func.count(DownloadLog.id)).where(DownloadLog.user_id == user_id)
            )).scalar_one()
            rows = (await s.execute(
                select(DownloadLog)
                .where(DownloadLog.user_id == user_id)
                .order_by(DownloadLog.created_at.desc())
                .offset(offset).limit(limit)
            )).scalars().all()
            return list(rows), total

    async def update(self, log_id: int, **kwargs: Any) -> DownloadLog | None:
        async with self._sf() as s:
            entry = await s.get(DownloadLog, log_id)
            if entry is None:
                return None
            for k, v in kwargs.items():
                setattr(entry, k, v)
            await s.commit()
            await s.refresh(entry)
            return entry

    async def retry(self, log_id: int) -> DownloadLog | None:
        return await self.update(log_id, status="pending")


class RateLimitRepo:
    """Per-user sliding window rate limiter backed by the DB."""

    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._sf = session_factory

    async def check_and_increment(
        self,
        user_id: int,
        limit_minute: int,
        limit_hour: int,
        limit_day: int,
    ) -> tuple[bool, str]:
        """Return (allowed, exceeded_window_name). Increments all windows atomically."""
        now = datetime.now(timezone.utc)
        windows = [
            ("minute", timedelta(minutes=1), limit_minute),
            ("hour",   timedelta(hours=1),   limit_hour),
            ("day",    timedelta(days=1),     limit_day),
        ]
        async with self._sf() as s:
            for window_name, delta, limit in windows:
                row = await s.get(RateLimit, {"user_id": user_id, "window": window_name})
                if row is None:
                    row = RateLimit(user_id=user_id, window=window_name, count=0, reset_at=now + delta)
                    s.add(row)
                elif row.reset_at <= now:
                    row.count = 0
                    row.reset_at = now + delta
                if row.count >= limit:
                    return False, window_name
                row.count += 1
            await s.commit()
        return True, ""
