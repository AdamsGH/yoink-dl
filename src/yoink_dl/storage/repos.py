"""Downloader plugin repositories.

All repositories that are dl-specific live here.
Repositories for core models (Group, ThreadPolicy, User, BotSetting)
are imported from yoink.core.db.repos - never duplicated here.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from yoink.core.db.models import BotSetting, User, UserRole
from yoink_dl.storage.models import (
    Cookie,
    DownloadLog,
    FileCache,
    NsfwDomain,
    NsfwKeyword,
    RateLimit,
    UserSettings as UserSettingsModel,
)

logger = logging.getLogger(__name__)

_FILE_CACHE_TTL_DAYS = 30


@dataclass
class UserSettings:
    """Flat dataclass used throughout the download/upload pipeline.

    Merges fields from core User and dl-specific UserSettings ORM model
    into a single immutable view that command handlers can pass around
    without touching the DB session.
    """
    user_id: int
    role: UserRole = UserRole.user
    language: str = "en"
    quality: str = "best"
    codec: str = "avc1"
    container: str = "mp4"
    proxy_enabled: bool = False
    proxy_url: str | None = None
    keyboard: str = "2x3"
    subs_enabled: bool = False
    subs_auto: bool = False
    subs_always_ask: bool = False
    subs_lang: str = "en"
    split_size: int = 2_043_000_000
    nsfw_blur: bool = True
    mediainfo: bool = False
    send_as_file: bool = False
    gallery_zip: bool = False
    args_json: dict[str, Any] = field(default_factory=dict)
    blocked: bool = False
    ban_until: datetime | None = None


def _user_to_settings(user: User, dl: UserSettingsModel | None = None) -> UserSettings:
    """Build a UserSettings dataclass from a core User and optional dl row."""
    now = datetime.now(timezone.utc)
    ban_until = user.ban_until
    if ban_until is not None and ban_until.tzinfo is None:
        ban_until = ban_until.replace(tzinfo=timezone.utc)
    blocked = (
        user.role == UserRole.banned
        or (ban_until is not None and ban_until > now)
    )
    return UserSettings(
        user_id=user.id,
        role=user.role,
        language=user.language,
        quality=dl.quality if dl else "best",
        codec=dl.codec if dl else "avc1",
        container=dl.container if dl else "mp4",
        proxy_enabled=dl.proxy_enabled if dl else False,
        proxy_url=dl.proxy_url if dl else None,
        keyboard=dl.keyboard if dl else "2x3",
        subs_enabled=dl.subs_enabled if dl else False,
        subs_auto=dl.subs_auto if dl else False,
        subs_always_ask=dl.subs_always_ask if dl else False,
        subs_lang=dl.subs_lang if dl else "en",
        split_size=dl.split_size if dl else 2_043_000_000,
        nsfw_blur=dl.nsfw_blur if dl else True,
        mediainfo=dl.mediainfo if dl else False,
        send_as_file=dl.send_as_file if dl else False,
        gallery_zip=dl.gallery_zip if dl else False,
        args_json=dl.args_json if dl else {},
        blocked=blocked,
        ban_until=ban_until,
    )


class UserSettingsRepo:
    """Reads core User + dl UserSettings model, exposes a flat UserSettings dataclass.

    This is the single entry point commands use to get per-user settings.
    """

    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._sf = session_factory

    async def get_or_create(
        self,
        user_id: int,
        group_id: int | None = None,
        first_name: str | None = None,
        username: str | None = None,
    ) -> UserSettings:
        async with self._sf() as s:
            user = await s.get(User, user_id)
            if user is None:
                # Determine initial role:
                # per-group auto_grant_role > global bot_access_mode
                role: UserRole | None = None
                if group_id is not None:
                    from yoink.core.db.models import Group
                    group = await s.get(Group, group_id)
                    if group is not None:
                        role = group.auto_grant_role
                if role is None:
                    row = await s.get(BotSetting, "bot_access_mode")
                    mode = row.value if row else "open"
                    role = UserRole.restricted if mode == "approved_only" else UserRole.user
                user = User(
                    id=user_id,
                    role=role,
                    first_name=first_name,
                    username=username,
                )
                s.add(user)
                await s.flush()
            else:
                # Update display name if provided and changed
                changed = False
                if first_name and user.first_name != first_name:
                    user.first_name = first_name
                    changed = True
                if username and user.username != username:
                    user.username = username
                    changed = True
                if changed:
                    await s.flush()
            dl = await s.get(UserSettingsModel, user_id)
            if dl is None:
                dl = UserSettingsModel(user_id=user_id)
                s.add(dl)
            await s.commit()
            await s.refresh(user)
            await s.refresh(dl)
            return _user_to_settings(user, dl)

    async def is_blocked(self, user_id: int) -> bool:
        async with self._sf() as s:
            user = await s.get(User, user_id)
            if user is None:
                return False
            if user.role == UserRole.banned:
                return True
            if user.ban_until is not None:
                ban_until = user.ban_until
                if ban_until.tzinfo is None:
                    ban_until = ban_until.replace(tzinfo=timezone.utc)
                if ban_until > datetime.now(timezone.utc):
                    return True
                await s.execute(
                    User.__table__.update()
                    .where(User.id == user_id)
                    .values(ban_until=None)
                )
                await s.commit()
            return False

    # Fields owned by core User model - routed to the right table in update()
    _USER_FIELDS = frozenset({"role", "ban_until", "username", "first_name", "language"})

    async def update(self, user_id: int, **kwargs: Any) -> UserSettings:
        """Update user fields, routing core fields to User and dl fields to UserSettings.

        Callers (e.g. admin.py) can pass role=, ban_until= alongside dl-specific
        fields and they will be written to the correct table.
        """
        user_kwargs = {k: v for k, v in kwargs.items() if k in self._USER_FIELDS}
        dl_kwargs = {k: v for k, v in kwargs.items() if k not in self._USER_FIELDS}

        async with self._sf() as s:
            user = await s.get(User, user_id)
            if user is None:
                user = User(id=user_id)
                s.add(user)
                await s.flush()
            for k, v in user_kwargs.items():
                setattr(user, k, v)

            dl = await s.get(UserSettingsModel, user_id)
            if dl is None:
                dl = UserSettingsModel(user_id=user_id)
                s.add(dl)
            for k, v in dl_kwargs.items():
                setattr(dl, k, v)
            if dl_kwargs:
                dl.updated_at = datetime.now(timezone.utc)

            await s.commit()
            await s.refresh(user)
            await s.refresh(dl)
            return _user_to_settings(user, dl)


@dataclass
class CachedFile:
    """In-memory view of a cached Telegram file_id."""
    cache_key: str
    file_id: str
    file_type: str       # "video" | "audio" | "document"
    title: str | None
    duration: float | None
    width: int | None
    height: int | None
    file_size: int | None


def make_cache_key(
    url: str,
    start_sec: int | None = None,
    end_sec: int | None = None,
    audio_only: bool = False,
) -> str:
    """Stable SHA-256 cache key base from a normalized URL, optional clip range, and media type."""
    parts = url
    if start_sec is not None and end_sec is not None:
        parts = f"{parts}@{start_sec}-{end_sec}"
    if audio_only:
        parts = f"{parts}#audio"
    return hashlib.sha256(parts.encode()).hexdigest()


def make_cache_key_n(base_key: str, index: int) -> str:
    """Cache key for the N-th item of a media group: '{base_key}:{index}'."""
    return f"{base_key}:{index}"


class FileCacheRepo:
    """Caches Telegram file_ids to avoid re-uploading identical content."""

    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._sf = session_factory

    def _row_to_cached(self, row: FileCache) -> CachedFile:
        return CachedFile(
            cache_key=row.cache_key,
            file_id=row.file_id,
            file_type=row.file_type,
            title=row.title,
            duration=row.duration,
            width=row.width,
            height=row.height,
            file_size=row.file_size,
        )

    async def get(self, cache_key: str) -> CachedFile | None:
        """Return a single cached file by exact key, or None if missing/expired."""
        now = datetime.now(timezone.utc)
        async with self._sf() as s:
            row = await s.get(FileCache, cache_key)
            if row is None:
                return None
            expires = row.expires_at
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            if expires <= now:
                return None
            return self._row_to_cached(row)

    async def get_group(self, base_key: str) -> list[CachedFile]:
        """Return all items for a URL: single file OR ordered media-group items.

        For a single file the base_key itself is stored (no ':N' suffix).
        For a media group the keys are '{base_key}:0', '{base_key}:1', ...
        Returns them ordered by index so the caller can send them in order.
        """
        now = datetime.now(timezone.utc)
        async with self._sf() as s:
            # Try single-file first (most common path, avoids LIKE scan)
            row = await s.get(FileCache, base_key)
            if row is not None:
                expires = row.expires_at
                if expires.tzinfo is None:
                    expires = expires.replace(tzinfo=timezone.utc)
                if expires > now:
                    return [self._row_to_cached(row)]

            # Media-group: keys like '{base_key}:0', '{base_key}:1', ...
            prefix = f"{base_key}:%"
            result = await s.execute(
                select(FileCache)
                .where(FileCache.cache_key.like(prefix), FileCache.expires_at > now)
                .order_by(FileCache.cache_key)
            )
            rows = result.scalars().all()
            return [self._row_to_cached(r) for r in rows]

    async def get_by_file_id(self, file_id: str) -> CachedFile | None:
        """Reverse lookup: find a cached entry by its Telegram file_id."""
        now = datetime.now(timezone.utc)
        async with self._sf() as s:
            result = await s.execute(
                select(FileCache)
                .where(FileCache.file_id == file_id, FileCache.expires_at > now)
                .limit(1)
            )
            row = result.scalar_one_or_none()
            return self._row_to_cached(row) if row else None

    async def put(
        self,
        cache_key: str,
        *,
        file_id: str,
        file_type: str,
        title: str | None = None,
        file_size: int | None = None,
        duration: float | None = None,
        url: str | None = None,
        width: int | None = None,
        height: int | None = None,
    ) -> None:
        """Store a single file_id. Used by pipeline for single-file downloads."""
        entry = CachedFile(
            cache_key=cache_key,
            file_id=file_id,
            file_type=file_type,
            title=title,
            duration=duration,
            width=width,
            height=height,
            file_size=file_size,
        )
        await self.store(entry)

    async def put_group(
        self,
        base_key: str,
        items: list[tuple[str, str]],  # [(file_id, file_type), ...]
        *,
        title: str | None = None,
        file_size: int | None = None,
    ) -> None:
        """Store a media group: each item gets key '{base_key}:{index}'.

        Existing items for this base_key are replaced atomically.
        """
        expires_at = datetime.now(timezone.utc) + timedelta(days=_FILE_CACHE_TTL_DAYS)
        async with self._sf() as s:
            # Delete old group entries for this base_key
            await s.execute(
                delete(FileCache).where(FileCache.cache_key.like(f"{base_key}:%"))
            )
            for i, (fid, ftype) in enumerate(items):
                key = make_cache_key_n(base_key, i)
                row = FileCache(
                    cache_key=key,
                    file_id=fid,
                    file_type=ftype,
                    title=title,
                    file_size=file_size,
                    expires_at=expires_at,
                )
                s.add(row)
            await s.commit()

    async def store(self, entry: CachedFile) -> None:
        expires_at = datetime.now(timezone.utc) + timedelta(days=_FILE_CACHE_TTL_DAYS)
        async with self._sf() as s:
            row = await s.get(FileCache, entry.cache_key)
            if row is None:
                row = FileCache(cache_key=entry.cache_key)
                s.add(row)
            row.file_id = entry.file_id
            row.file_type = entry.file_type
            row.title = entry.title
            row.duration = entry.duration
            row.width = entry.width
            row.height = entry.height
            row.file_size = entry.file_size
            row.expires_at = expires_at
            await s.commit()

    async def delete(self, cache_key: str) -> bool:
        async with self._sf() as s:
            result = await s.execute(
                delete(FileCache).where(FileCache.cache_key == cache_key)
            )
            await s.commit()
            return result.rowcount > 0

    async def evict_expired(self) -> int:
        now = datetime.now(timezone.utc)
        async with self._sf() as s:
            result = await s.execute(
                delete(FileCache).where(FileCache.expires_at <= now)
            )
            await s.commit()
            return result.rowcount


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
        """Write a log entry from a bot command handler. Silently swallows errors."""
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


class CookieRepo:
    """Stores per-user, per-domain Netscape cookies for yt-dlp."""

    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._sf = session_factory

    async def get(self, user_id: int, domain: str) -> Cookie | None:
        async with self._sf() as s:
            result = await s.execute(
                select(Cookie).where(Cookie.user_id == user_id, Cookie.domain == domain)
            )
            return result.scalar_one_or_none()

    async def upsert(self, user_id: int, domain: str, content: str) -> Cookie:
        async with self._sf() as s:
            result = await s.execute(
                select(Cookie).where(Cookie.user_id == user_id, Cookie.domain == domain)
            )
            cookie = result.scalar_one_or_none()
            if cookie is None:
                cookie = Cookie(user_id=user_id, domain=domain, content=content)
                s.add(cookie)
            else:
                cookie.content = content
                cookie.updated_at = datetime.now(timezone.utc)
            await s.commit()
            await s.refresh(cookie)
            return cookie

    async def list_for_user(self, user_id: int) -> list[Cookie]:
        async with self._sf() as s:
            result = await s.execute(select(Cookie).where(Cookie.user_id == user_id))
            return list(result.scalars().all())

    async def delete(self, user_id: int, domain: str) -> bool:
        async with self._sf() as s:
            result = await s.execute(
                select(Cookie).where(Cookie.user_id == user_id, Cookie.domain == domain)
            )
            cookie = result.scalar_one_or_none()
            if cookie is None:
                return False
            await s.delete(cookie)
            await s.commit()
            return True


class NsfwRepo:
    """CRUD for NSFW domain and keyword blocklists."""

    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._sf = session_factory

    async def list_domains(self) -> list[NsfwDomain]:
        async with self._sf() as s:
            result = await s.execute(select(NsfwDomain).order_by(NsfwDomain.domain))
            return list(result.scalars().all())

    async def list_keywords(self) -> list[NsfwKeyword]:
        async with self._sf() as s:
            result = await s.execute(select(NsfwKeyword).order_by(NsfwKeyword.keyword))
            return list(result.scalars().all())

    async def add_domain(self, domain: str, note: str | None = None) -> NsfwDomain:
        async with self._sf() as s:
            obj = NsfwDomain(domain=domain, note=note)
            s.add(obj)
            await s.commit()
            await s.refresh(obj)
            return obj

    async def add_keyword(self, keyword: str, note: str | None = None) -> NsfwKeyword:
        async with self._sf() as s:
            obj = NsfwKeyword(keyword=keyword, note=note)
            s.add(obj)
            await s.commit()
            await s.refresh(obj)
            return obj

    async def delete_domain(self, domain_id: int) -> bool:
        async with self._sf() as s:
            obj = await s.get(NsfwDomain, domain_id)
            if obj is None:
                return False
            await s.delete(obj)
            await s.commit()
            return True

    async def delete_keyword(self, keyword_id: int) -> bool:
        async with self._sf() as s:
            obj = await s.get(NsfwKeyword, keyword_id)
            if obj is None:
                return False
            await s.delete(obj)
            await s.commit()
            return True
