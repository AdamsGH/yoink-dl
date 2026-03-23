"""Cookie manager - per-user and global Netscape cookie files stored in PostgreSQL."""
from __future__ import annotations

import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import select, delete, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from yoink.core.db.models import User
from yoink_dl.storage.models import Cookie

logger = logging.getLogger(__name__)

_NETSCAPE_HEADER = "# Netscape HTTP Cookie File"


def _domain_from_url(url: str) -> str:
    """Extract bare domain (e.g. 'youtube.com') from a URL."""
    host = urlparse(url).netloc.lower()
    host = host.split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    return host


def validate_netscape(content: str) -> bool:
    """Return True if content looks like a valid Netscape cookie file."""
    for line in content.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            parts = line.split("\t")
            if len(parts) >= 7:
                return True
    return False


class CookieManager:
    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._factory = session_factory

    async def _ensure_user(self, session, user_id: int) -> None:
        """Create user row if it doesn't exist (cookies FK depends on it)."""
        user = await session.get(User, user_id)
        if user is None:
            session.add(User(id=user_id))
            await session.flush()

    async def store(self, user_id: int, domain: str, content: str) -> None:
        """Save or replace a cookie for (user_id, domain)."""
        async with self._factory() as session:
            await self._ensure_user(session, user_id)
            result = await session.execute(
                select(Cookie).where(Cookie.user_id == user_id, Cookie.domain == domain)
            )
            cookie = result.scalar_one_or_none()
            if cookie is None:
                cookie = Cookie(user_id=user_id, domain=domain, content=content, is_valid=True)
                session.add(cookie)
            else:
                cookie.content = content
                cookie.is_valid = True
                cookie.updated_at = datetime.now(timezone.utc)
            await session.commit()
        logger.info("Stored cookie for user=%d domain=%s", user_id, domain)

    async def delete(self, user_id: int, domain: str) -> bool:
        """Remove cookie for (user_id, domain). Returns True if row existed."""
        async with self._factory() as session:
            result = await session.execute(
                delete(Cookie)
                .where(Cookie.user_id == user_id, Cookie.domain == domain)
                .returning(Cookie.id)
            )
            await session.commit()
            return result.rowcount > 0

    async def clear(self, user_id: int) -> int:
        """Remove all cookies for a user. Returns count removed."""
        async with self._factory() as session:
            result = await session.execute(
                delete(Cookie).where(Cookie.user_id == user_id)
            )
            await session.commit()
            return result.rowcount

    async def list_domains(self, user_id: int) -> list[str]:
        async with self._factory() as session:
            result = await session.execute(
                select(Cookie.domain)
                .where(Cookie.user_id == user_id, Cookie.is_valid.is_(True))
                .order_by(Cookie.domain)
            )
            return list(result.scalars())

    async def get_content(self, user_id: int, domain: str) -> str | None:
        """Return raw cookie content for (user_id, domain), or None."""
        async with self._factory() as session:
            result = await session.execute(
                select(Cookie.content)
                .where(
                    Cookie.user_id == user_id,
                    Cookie.domain == domain,
                    Cookie.is_valid.is_(True),
                )
            )
            return result.scalar_one_or_none()

    async def get_path_for_url(
        self,
        user_id: int,
        url: str,
        global_user_id: int | None = None,
        no_cookie_domains: list[str] | None = None,
    ) -> Path | None:
        """
        Write matching cookie content to a temp file and return its path.
        Caller is responsible for deleting the file after use.

        Lookup order:
          1. Check no_cookie_domains  - skip cookies entirely if domain matches
          2. User's cookie for the URL's domain
          3. Global cookie (global_user_id=owner) for the domain
          4. None
        """
        domain = _domain_from_url(url)

        if no_cookie_domains:
            for pattern in no_cookie_domains:
                p = pattern.lower().removeprefix("www.")
                if domain == p or domain.endswith("." + p):
                    logger.debug("Skipping cookies for no-cookie domain=%s", domain)
                    return None

        content = await self.get_content(user_id, domain)

        if content is None and global_user_id is not None and global_user_id != user_id:
            content = await self.get_content(global_user_id, domain)
            if content:
                logger.debug("Using global cookie for domain=%s user=%d", domain, user_id)

        if content is None:
            return None

        fd, tmp_str = tempfile.mkstemp(suffix=".txt", prefix="ck_")
        tmp = Path(tmp_str)
        try:
            os.close(fd)
            tmp.write_text(content, encoding="utf-8")
        except Exception:
            tmp.unlink(missing_ok=True)
            raise
        return tmp

    async def mark_invalid(self, user_id: int, domain: str) -> None:
        """Flag a cookie as invalid (e.g. after a 403)."""
        async with self._factory() as session:
            result = await session.execute(
                select(Cookie).where(Cookie.user_id == user_id, Cookie.domain == domain)
            )
            cookie = result.scalar_one_or_none()
            if cookie is not None:
                cookie.is_valid = False
                cookie.updated_at = datetime.now(timezone.utc)
                await session.commit()
        logger.warning("Marked cookie invalid for user=%d domain=%s", user_id, domain)
