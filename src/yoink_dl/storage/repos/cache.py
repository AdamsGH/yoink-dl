"""File cache repository - avoids re-uploading identical Telegram content."""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import delete, select

from yoink_dl.storage.models import FileCache

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker

logger = logging.getLogger(__name__)

_FILE_CACHE_TTL_DAYS = 30
_MIN_CACHEABLE_MEDIA_BYTES = 1024
_MEDIA_FILE_TYPES = frozenset({"animation", "audio", "video", "voice"})


@dataclass
class CachedFile:
    """In-memory view of a cached Telegram file_id."""
    cache_key: str
    file_id: str
    file_type: str
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

    @staticmethod
    def _row_to_cached(row: FileCache) -> CachedFile:
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

    @staticmethod
    def _is_usable(row: FileCache) -> bool:
        return not (
            row.file_type in _MEDIA_FILE_TYPES
            and row.file_size is not None
            and row.file_size < _MIN_CACHEABLE_MEDIA_BYTES
        )

    async def get(self, base_key: str) -> list[CachedFile]:
        """Return cached files for a URL.

        For a single file the base_key itself is stored (no ':N' suffix).
        For a media group the keys are '{base_key}:0', '{base_key}:1', ...
        Returns them ordered by index so the caller can send them in order.
        """
        now = datetime.now(UTC)
        async with self._sf() as s:
            row = await s.get(FileCache, base_key)
            if row is not None:
                expires = row.expires_at
                if expires.tzinfo is None:
                    expires = expires.replace(tzinfo=UTC)
                if expires > now and self._is_usable(row):
                    return [self._row_to_cached(row)]
                if not self._is_usable(row):
                    logger.warning(
                        "Evicting invalid media cache entry %s: type=%s size=%s",
                        row.cache_key, row.file_type, row.file_size,
                    )
                    await s.delete(row)
                    await s.commit()

            prefix = f"{base_key}:%"
            result = await s.execute(
                select(FileCache)
                .where(FileCache.cache_key.like(prefix), FileCache.expires_at > now)
                .order_by(FileCache.cache_key)
            )
            rows = result.scalars().all()
            if rows and not all(self._is_usable(item) for item in rows):
                logger.warning("Evicting invalid media-group cache entries for %s", base_key)
                await s.execute(delete(FileCache).where(FileCache.cache_key.like(prefix)))
                await s.commit()
                return []
            return [self._row_to_cached(r) for r in rows]

    async def get_by_file_id(self, file_id: str) -> CachedFile | None:
        """Reverse lookup: find a cached entry by its Telegram file_id."""
        now = datetime.now(UTC)
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
            cache_key=cache_key, file_id=file_id, file_type=file_type,
            title=title, duration=duration, width=width, height=height, file_size=file_size,
        )
        await self.store(entry)

    async def put_group(
        self,
        base_key: str,
        items: list[tuple[str, str]],
        *,
        title: str | None = None,
        file_size: int | None = None,
    ) -> None:
        """Store a media group: each item gets key '{base_key}:{index}'.

        Existing items for this base_key are replaced atomically.
        """
        expires_at = datetime.now(UTC) + timedelta(days=_FILE_CACHE_TTL_DAYS)
        async with self._sf() as s:
            await s.execute(delete(FileCache).where(FileCache.cache_key.like(f"{base_key}:%")))
            for i, (fid, ftype) in enumerate(items):
                key = make_cache_key_n(base_key, i)
                s.add(FileCache(
                    cache_key=key, file_id=fid, file_type=ftype,
                    title=title, file_size=file_size, expires_at=expires_at,
                ))
            await s.commit()

    async def store(self, entry: CachedFile) -> None:
        expires_at = datetime.now(UTC) + timedelta(days=_FILE_CACHE_TTL_DAYS)
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
            result = await s.execute(delete(FileCache).where(FileCache.cache_key == cache_key))
            await s.commit()
            return result.rowcount > 0

    async def evict_expired(self) -> int:
        now = datetime.now(UTC)
        async with self._sf() as s:
            result = await s.execute(delete(FileCache).where(FileCache.expires_at <= now))
            await s.commit()
            return result.rowcount
