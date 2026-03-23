"""
NSFW detection service.

Three detection layers (short-circuits on first match):
  1. Domain   - URL domain in nsfw_domains table
  2. URL kw   - delimiter-aware keyword scan of URL path/query
  3. Meta kw  - title / description / tags from yt-dlp info dict

The NsfwChecker is initialised once at bot startup with a session_factory,
caches the lists in memory, and exposes reload() for hot-refresh.

Spoiler logic (should_apply_spoiler):
  - Content must be NSFW
  - Only in private chats (groups use a separate allow/block policy)
  - User must have nsfw_blur=True (default)
"""
from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy import select

from yoink_dl.storage.models import NsfwDomain, NsfwKeyword

logger = logging.getLogger(__name__)


class NsfwChecker:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory
        self._domains: frozenset[str] = frozenset()
        self._keywords: frozenset[str] = frozenset()
        self._text_re: re.Pattern[str] | None = None
        self._url_re: re.Pattern[str] | None = None

    # Loader

    async def load(self) -> None:
        """Load lists from DB into memory. Call at startup and after edits."""
        async with self._sf() as s:
            domains_rows = (await s.execute(select(NsfwDomain.domain))).scalars().all()
            keyword_rows = (await s.execute(select(NsfwKeyword.keyword))).scalars().all()

        self._domains = frozenset(d.lower() for d in domains_rows)
        self._keywords = frozenset(k.lower() for k in keyword_rows)
        self._compile()
        logger.info(
            "nsfw: loaded %d domains, %d keywords",
            len(self._domains), len(self._keywords),
        )

    async def reload(self) -> dict[str, int]:
        """Hot-reload from DB. Returns counts."""
        await self.load()
        return {"domains": len(self._domains), "keywords": len(self._keywords)}

    # DB helpers (used by admin commands / API)

    async def add_domain(self, domain: str, note: str | None = None) -> NsfwDomain:
        domain = domain.lower().removeprefix("www.")
        async with self._sf() as s:
            existing = (await s.execute(
                select(NsfwDomain).where(NsfwDomain.domain == domain)
            )).scalar_one_or_none()
            if existing:
                return existing
            row = NsfwDomain(domain=domain, note=note)
            s.add(row)
            await s.commit()
            await s.refresh(row)
        await self.load()
        return row

    async def remove_domain(self, domain: str) -> bool:
        domain = domain.lower().removeprefix("www.")
        async with self._sf() as s:
            row = (await s.execute(
                select(NsfwDomain).where(NsfwDomain.domain == domain)
            )).scalar_one_or_none()
            if not row:
                return False
            await s.delete(row)
            await s.commit()
        await self.load()
        return True

    async def add_keyword(self, keyword: str, note: str | None = None) -> NsfwKeyword:
        keyword = keyword.lower()
        async with self._sf() as s:
            existing = (await s.execute(
                select(NsfwKeyword).where(NsfwKeyword.keyword == keyword)
            )).scalar_one_or_none()
            if existing:
                return existing
            row = NsfwKeyword(keyword=keyword, note=note)
            s.add(row)
            await s.commit()
            await s.refresh(row)
        await self.load()
        return row

    async def remove_keyword(self, keyword: str) -> bool:
        keyword = keyword.lower()
        async with self._sf() as s:
            row = (await s.execute(
                select(NsfwKeyword).where(NsfwKeyword.keyword == keyword)
            )).scalar_one_or_none()
            if not row:
                return False
            await s.delete(row)
            await s.commit()
        await self.load()
        return True

    async def list_domains(self) -> list[NsfwDomain]:
        async with self._sf() as s:
            return list((await s.execute(
                select(NsfwDomain).order_by(NsfwDomain.domain)
            )).scalars().all())

    async def list_keywords(self) -> list[NsfwKeyword]:
        async with self._sf() as s:
            return list((await s.execute(
                select(NsfwKeyword).order_by(NsfwKeyword.keyword)
            )).scalars().all())

    # Detection

    def is_nsfw_domain(self, url: str) -> bool:
        from yoink_dl.url.domains import extract_domain
        domain = extract_domain(url)
        if not domain:
            return False
        for d in self._domains:
            if domain == d or domain.endswith("." + d):
                return True
        return False

    def check(
        self,
        url: str,
        info: dict[str, Any] | None = None,
    ) -> tuple[bool, str]:
        """
        Returns (is_nsfw, reason).
        reason is a short string for logging/admin debug.
        """
        # Layer 1 - domain
        if self.is_nsfw_domain(url):
            from yoink_dl.url.domains import extract_domain
            return True, f"domain:{extract_domain(url)}"

        # Layer 2 - URL keywords
        if self._url_re and self._url_re.search(url):
            m = self._url_re.search(url)
            return True, f"url_kw:{m.group(0)[:40] if m else '?'}"

        # Layer 3 - metadata keywords
        if info and self._text_re:
            title = info.get("title") or ""
            description = (info.get("description") or "")[:2000]  # cap long descriptions
            tags = " ".join(info.get("tags") or [])
            categories = " ".join(info.get("categories") or [])
            combined = f"{title} {description} {tags} {categories}"
            m = self._text_re.search(combined)
            if m:
                return True, f"meta_kw:{m.group(0)[:40]}"

        return False, ""

    # Spoiler decision

    @staticmethod
    def should_apply_spoiler(
        is_nsfw_content: bool,
        user_nsfw_blur: bool,
        is_private_chat: bool,
    ) -> bool:
        """
        True when Telegram has_spoiler should be set.

        Groups never get spoiler - NSFW in groups is handled by
        nsfw_allowed flag on the Group model (block/allow at URL level).
        """
        if not is_nsfw_content:
            return False
        if not is_private_chat:
            return False
        return user_nsfw_blur

    # Internal

    def _compile(self) -> None:
        if not self._keywords:
            self._text_re = self._url_re = None
            return

        escaped = sorted(re.escape(kw) for kw in self._keywords)

        # Word-boundary regex for prose (title, description, tags)
        self._text_re = re.compile(
            r"\b(" + "|".join(escaped) + r")\b",
            flags=re.IGNORECASE,
        )

        # Delimiter-aware regex for URLs
        url_parts = []
        for kw in sorted(self._keywords):
            words = [re.escape(w) for w in kw.split() if w]
            if not words:
                continue
            core = r"[^A-Za-z0-9]+".join(words)
            url_parts.append(rf"(?<![A-Za-z0-9])(?:{core})(?![A-Za-z0-9])")
        self._url_re = (
            re.compile("|".join(url_parts), flags=re.IGNORECASE)
            if url_parts else None
        )
