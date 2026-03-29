"""Cookie and NSFW repositories."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from yoink_dl.storage.models import Cookie, NsfwDomain, NsfwKeyword


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
