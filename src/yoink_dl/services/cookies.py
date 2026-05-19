"""Cookie manager - per-user and pool Netscape cookie files stored in PostgreSQL."""
from __future__ import annotations

import itertools
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import async_sessionmaker

from yoink.core.db.models import User
from yoink_dl.storage.models import Cookie

logger = logging.getLogger(__name__)

_NETSCAPE_HEADER = "# Netscape HTTP Cookie File"

from yoink_dl.services.cookies_netscape import (  # noqa: E402
    _domain_from_url,
    validate_netscape,
    _parse_netscape_cookies,
    extract_account_label,
    _merge_netscape_updates,
    _write_tmp,
    _merge_set_cookie,
)
from yoink_dl.services.yttv_oauth import OAuthTokens, decode_content, is_oauth_content  # noqa: E402


class _CookieCycle:
    """Thin wrapper around itertools.cycle that tracks the ids of its items.

    itertools.cycle is a C extension and does not allow arbitrary attribute
    assignment, so we keep the ids list separately.
    """

    def __init__(self, items: list) -> None:
        self.ids: list[int] = [getattr(item, "id", item) for item in items]
        self._cycle = itertools.cycle(items)

    def __next__(self):
        return next(self._cycle)


class CookieManager:
    def __init__(
        self,
        session_factory: async_sessionmaker,
        *,
        account_info_timeout: float = 10.0,
    ) -> None:
        self._factory = session_factory
        self._account_info_timeout = account_info_timeout
        # In-memory round-robin counters keyed by domain: pool cookie ids cycle
        self._pool_iters: dict[str, _CookieCycle] = {}
        self._pool_lock = threading.Lock()

    # Helpers

    async def _ensure_user(self, session, user_id: int) -> None:
        user = await session.get(User, user_id)
        if user is None:
            session.add(User(id=user_id))
            await session.flush()

    # Personal cookies (user-owned, is_pool=False)

    async def store(self, user_id: int, domain: str, content: str) -> None:
        """Save or replace a personal cookie for (user_id, domain)."""
        async with self._factory() as session:
            await self._ensure_user(session, user_id)
            row = (await session.execute(
                select(Cookie).where(
                    Cookie.user_id == user_id,
                    Cookie.domain == domain,
                    Cookie.is_pool.is_(False),
                )
            )).scalar_one_or_none()
            if row is None:
                row = Cookie(user_id=user_id, domain=domain, content=content,
                             is_valid=True, is_pool=False)
                session.add(row)
            else:
                row.content = content
                row.is_valid = True
                row.updated_at = datetime.now(timezone.utc)
            await session.commit()
        logger.info("Stored personal cookie: user=%d domain=%s", user_id, domain)

    async def delete(self, user_id: int, domain: str) -> bool:
        async with self._factory() as session:
            result = await session.execute(
                delete(Cookie)
                .where(Cookie.user_id == user_id, Cookie.domain == domain,
                       Cookie.is_pool.is_(False))
                .returning(Cookie.id)
            )
            await session.commit()
            return result.rowcount > 0

    async def clear(self, user_id: int) -> int:
        async with self._factory() as session:
            result = await session.execute(
                delete(Cookie).where(Cookie.user_id == user_id, Cookie.is_pool.is_(False))
            )
            await session.commit()
            return result.rowcount

    async def list_domains(self, user_id: int) -> list[str]:
        async with self._factory() as session:
            result = await session.execute(
                select(Cookie.domain)
                .where(Cookie.user_id == user_id, Cookie.is_valid.is_(True),
                       Cookie.is_pool.is_(False))
                .order_by(Cookie.domain)
            )
            return list(result.scalars())

    async def get_content(self, user_id: int, domain: str) -> str | None:
        async with self._factory() as session:
            result = await session.execute(
                select(Cookie.content)
                .where(Cookie.user_id == user_id, Cookie.domain == domain,
                       Cookie.is_valid.is_(True), Cookie.is_pool.is_(False))
            )
            return result.scalar_one_or_none()

    async def mark_invalid(self, user_id: int, domain: str) -> None:
        """Flag a personal cookie as invalid (e.g. after a 403)."""
        async with self._factory() as session:
            row = (await session.execute(
                select(Cookie).where(Cookie.user_id == user_id, Cookie.domain == domain,
                                     Cookie.is_pool.is_(False))
            )).scalar_one_or_none()
            if row is not None:
                row.is_valid = False
                row.updated_at = datetime.now(timezone.utc)
                await session.commit()
        logger.warning("Marked cookie invalid: user=%d domain=%s", user_id, domain)

    # Pool cookies (is_pool=True, shared across users)

    @staticmethod
    def _extract_session_key(domain: str, content: str) -> str | None:
        """
        Extract a stable per-account identity key from cookie content.
        Used for deduplication - same account = same key regardless of expiry/other cookie changes.
        """
        cookies = _parse_netscape_cookies(content)
        bare = domain.removeprefix("www.")

        # YouTube / Google: SAPISID is stable per Google account
        if bare in ("youtube.com", "google.com") or bare.endswith((".youtube.com", ".google.com")):
            return cookies.get("SAPISID") or cookies.get("__Secure-3PAPISID")

        # Instagram: ds_user_id is numeric user id
        if bare in ("instagram.com",) or bare.endswith(".instagram.com"):
            return cookies.get("ds_user_id") or cookies.get("sessionid")

        # Twitter/X: twid contains user id
        if bare in ("twitter.com", "x.com") or bare.endswith((".twitter.com", ".x.com")):
            return cookies.get("twid") or cookies.get("auth_token")

        # TikTok: uid_tt is stable
        if bare in ("tiktok.com",) or bare.endswith(".tiktok.com"):
            return cookies.get("uid_tt") or cookies.get("sid_tt")

        # Facebook: c_user is numeric user id
        if bare in ("facebook.com",) or bare.endswith(".facebook.com"):
            return cookies.get("c_user") or cookies.get("xs")

        # Generic: try common session cookie names
        for name in ("sessionid", "session_id", "auth_token", "access_token", "sid"):
            if name in cookies:
                return cookies[name]

        return None

    async def store_pool(self, owner_id: int, domain: str, content: str) -> Cookie:
        """Add or update a pool cookie. Deduplicates by per-account session key (e.g. SAPISID)."""
        from yoink_dl.services.cookie_account import fetch_account_info  # noqa: PLC0415
        import hashlib  # noqa: PLC0415

        content_hash = hashlib.sha256(content.encode()).hexdigest()
        session_key = self._extract_session_key(domain, content)

        info = None
        try:
            info = await fetch_account_info(domain, content, timeout=self._account_info_timeout)
        except Exception:
            logger.debug("fetch_account_info failed for %s", domain, exc_info=True)

        label = (info.name if info else None) or extract_account_label(domain, content)
        avatar_url = info.avatar_url if info else None
        now = datetime.now(timezone.utc)

        async with self._factory() as session:
            await self._ensure_user(session, owner_id)

            # Find existing pool cookie for same account:
            # 1. by session_key (stable across re-exports)
            # 2. fallback by content_hash (exact same file)
            existing = None
            if session_key:
                existing = (await session.execute(
                    select(Cookie).where(
                        Cookie.user_id == owner_id,
                        Cookie.domain == domain,
                        Cookie.is_pool.is_(True),
                        Cookie.session_key == session_key,
                    )
                )).scalar_one_or_none()

            if existing is None:
                existing = (await session.execute(
                    select(Cookie).where(
                        Cookie.user_id == owner_id,
                        Cookie.domain == domain,
                        Cookie.is_pool.is_(True),
                        Cookie.content_hash == content_hash,
                    )
                )).scalar_one_or_none()

            if existing is not None:
                existing.content = content
                existing.content_hash = content_hash
                existing.session_key = session_key
                existing.is_valid = True
                existing.updated_at = now
                if label:
                    existing.label = label
                if avatar_url:
                    existing.avatar_url = avatar_url
                await session.commit()
                await session.refresh(existing)
                logger.info("Updated pool cookie: owner=%d domain=%s id=%d", owner_id, domain, existing.id)
                return existing

            row = Cookie(
                user_id=owner_id, domain=domain, content=content,
                content_hash=content_hash, session_key=session_key,
                is_valid=True, is_pool=True, label=label, avatar_url=avatar_url,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)

        with self._pool_lock:
            self._pool_iters.pop(domain, None)
        logger.info("Added pool cookie: owner=%d domain=%s id=%d", owner_id, domain, row.id)
        return row

    async def delete_pool(self, cookie_id: int) -> bool:
        async with self._factory() as session:
            result = await session.execute(
                delete(Cookie)
                .where(Cookie.id == cookie_id, Cookie.is_pool.is_(True))
                .returning(Cookie.domain)
            )
            row = result.fetchone()
            await session.commit()
            if row:
                with self._pool_lock:
                    self._pool_iters.pop(row[0], None)
            return row is not None

    async def refresh_pool_labels(self) -> int:
        """Fetch real account info for all pool cookies missing a label. Returns count updated."""
        from yoink_dl.services.cookie_account import fetch_account_info  # noqa: PLC0415
        updated = 0
        async with self._factory() as session:
            rows = list((await session.execute(
                select(Cookie).where(Cookie.is_pool.is_(True))
            )).scalars().all())
            for row in rows:
                try:
                    info = await fetch_account_info(row.domain, row.content, timeout=self._account_info_timeout)
                except Exception:
                    info = None
                label = (info.name if info else None) or extract_account_label(row.domain, row.content)
                avatar_url = info.avatar_url if info else None
                if label != row.label or avatar_url != row.avatar_url:
                    row.label = label
                    row.avatar_url = avatar_url
                    updated += 1
            if updated:
                await session.commit()
        return updated

    async def list_pool(self, domain: str | None = None) -> list[Cookie]:
        async with self._factory() as session:
            q = select(Cookie).where(Cookie.is_pool.is_(True))
            if domain:
                q = q.where(Cookie.domain == domain)
            q = q.order_by(Cookie.domain, Cookie.id)
            return list((await session.execute(q)).scalars().all())

    async def get_pool_cookie(self, domain: str) -> Cookie | None:
        """
        Return the next valid pool cookie for domain using round-robin.
        Returns None if no valid pool cookies exist for the domain.
        """
        async with self._factory() as session:
            rows = (await session.execute(
                select(Cookie)
                .where(Cookie.is_pool.is_(True), Cookie.domain == domain,
                       Cookie.is_valid.is_(True))
                .order_by(Cookie.id)
            )).scalars().all()

        if not rows:
            return None

        with self._pool_lock:
            cycle = self._pool_iters.get(domain)
            current_ids = [r.id for r in rows]
            if cycle is None or cycle.ids != current_ids:
                cycle = _CookieCycle(rows)
                self._pool_iters[domain] = cycle
            return next(cycle)

    async def mark_pool_invalid(self, cookie_id: int) -> None:
        async with self._factory() as session:
            row = await session.get(Cookie, cookie_id)
            if row is not None and row.is_pool:
                row.is_valid = False
                row.updated_at = datetime.now(timezone.utc)
                await session.commit()
        with self._pool_lock:
            # Force cycle rebuild on next request
            self._pool_iters.clear()
        logger.warning("Marked pool cookie invalid: id=%d", cookie_id)

    # Set-Cookie update (works for both personal and pool)

    async def update_from_headers(self, cookie_id: int, set_cookie_header: str) -> bool:
        """
        Merge Set-Cookie response header into stored cookie content.
        Returns True if content actually changed.
        """
        async with self._factory() as session:
            row = await session.get(Cookie, cookie_id)
            if row is None:
                return False
            updated = _merge_set_cookie(row.content, set_cookie_header)
            if updated == row.content:
                return False
            row.content = updated
            row.updated_at = datetime.now(timezone.utc)
            await session.commit()
        logger.debug("Updated cookie content from Set-Cookie: id=%d", cookie_id)
        return True

    async def validate_live(self, cookie_id: int) -> bool:
        """
        Validate a cookie by calling the platform API with it.
        Merges any Set-Cookie tokens returned back into the DB row (rolling refresh).
        Returns True if the cookie is authenticated.
        """
        from yoink_dl.services.cookie_account import fetch_account_info, _fetch_youtube  # noqa: PLC0415

        async with self._factory() as session:
            row = await session.get(Cookie, cookie_id)
            if row is None:
                return False
            domain = row.domain
            content = row.content

        bare = domain.removeprefix("www.")
        new_cookies: dict[str, str] = {}
        is_valid = False

        try:
            if bare in ("youtube.com", "google.com") or bare.endswith((".youtube.com", ".google.com")):
                result = await _fetch_youtube(content, return_set_cookie=True, timeout=self._account_info_timeout)
                info, new_cookies = result  # type: ignore[misc]
                is_valid = info is not None
            else:
                info = await fetch_account_info(domain, content, timeout=self._account_info_timeout)
                is_valid = info is not None
        except Exception:
            logger.debug("validate_live: fetch failed for %s", domain, exc_info=True)
            is_valid = False

        # Merge rotated tokens back into DB content (pplx-style rolling refresh)
        updated_content = content
        if new_cookies:
            updated_content = _merge_netscape_updates(content, new_cookies)

        now = datetime.now(timezone.utc)
        async with self._factory() as session:
            row = await session.get(Cookie, cookie_id)
            if row is not None:
                row.is_valid = is_valid
                row.validated_at = now
                if updated_content != content:
                    row.content = updated_content
                    row.updated_at = now
                await session.commit()

        logger.info("validate_live: id=%d domain=%s is_valid=%s new_cookies=%s",
                    cookie_id, domain, is_valid, list(new_cookies.keys()))
        return is_valid

    async def sync_from_file(self, cookie_id: int, path: Path) -> bool:
        """
        Read a cookie file (written by yt-dlp during download) and sync
        its content back to the DB row. Returns True if content changed.

        Skips the update if the file looks invalid (empty or shorter than
        the stored content by more than 20%) to avoid overwriting working
        cookies with a truncated/error file.
        """
        try:
            new_content = path.read_text(encoding="utf-8")
        except OSError:
            return False
        if not validate_netscape(new_content):
            logger.debug("sync_from_file: skipping invalid cookie file: id=%d path=%s", cookie_id, path)
            return False
        async with self._factory() as session:
            row = await session.get(Cookie, cookie_id)
            if row is None:
                return False
            if new_content == row.content:
                return False
            # Guard: don't overwrite a large cookie file with a suspiciously small one
            if len(new_content) < len(row.content) * 0.8:
                logger.warning(
                    "sync_from_file: new content is %.0f%% of original, skipping: id=%d",
                    100 * len(new_content) / max(len(row.content), 1), cookie_id,
                )
                return False
            row.content = new_content
            row.updated_at = datetime.now(timezone.utc)
            await session.commit()
        logger.debug("Synced cookie from file: id=%d path=%s", cookie_id, path)
        return True

    # Main lookup: returns (tmp_path, cookie_id) for pipeline use

    async def get_path_for_url(
        self,
        user_id: int,
        url: str,
        use_pool: bool = False,
        no_cookie_domains: list[str] | None = None,
    ) -> tuple[Path, int] | None:
        """
        Resolve the best cookie for a URL and write it to a temp file.

        Lookup order:
          1. User's personal cookie for the domain
          2. Pool cookie (round-robin) - only if use_pool=True
          3. None

        Returns (tmp_path, cookie_id) so the caller can sync back after download.
        Caller is responsible for deleting the tmp file.
        """
        domain = _domain_from_url(url)

        if no_cookie_domains:
            for pattern in no_cookie_domains:
                p = pattern.lower().removeprefix("www.")
                if domain == p or domain.endswith("." + p):
                    logger.debug("Skipping cookies for no-cookie domain=%s", domain)
                    return None

        # 1. Personal cookie
        async with self._factory() as session:
            personal = (await session.execute(
                select(Cookie).where(
                    Cookie.user_id == user_id,
                    Cookie.domain == domain,
                    Cookie.is_valid.is_(True),
                    Cookie.is_pool.is_(False),
                )
            )).scalar_one_or_none()

        if not use_pool:
            row = personal
        else:
            # With pool access: rotate across personal + pool cookies combined
            pool_cookie = await self.get_pool_cookie(domain)
            if personal is None and pool_cookie is None:
                row = None
            elif personal is None:
                row = pool_cookie
            elif pool_cookie is None:
                row = personal
            else:
                # Both available - rotate: personal first, then pool on next call
                row = await self._rotate_personal_and_pool(user_id, domain, personal, pool_cookie)

        if row is None:
            return None

        # OAuth tokens are not Netscape format - skip passing as cookiefile
        if is_oauth_content(row.content):
            logger.debug("Skipping OAuth token as cookiefile: id=%d domain=%s", row.id, domain)
            return None

        if row.is_pool:
            logger.debug("Using pool cookie: id=%d domain=%s user=%d", row.id, domain, user_id)
        tmp = _write_tmp(row.content)
        return tmp, row.id

    async def get_oauth_tokens_for_url(
        self,
        user_id: int,
        url: str,
    ) -> "OAuthTokens | None":
        """
        Return fresh OAuthTokens for the URL's domain if the user has an OAuth entry.
        Refreshes automatically when expired. Returns None if no OAuth entry exists.
        """
        domain = _domain_from_url(url)

        async with self._factory() as session:
            row = (await session.execute(
                select(Cookie).where(
                    Cookie.user_id == user_id,
                    Cookie.domain == domain,
                    Cookie.is_pool.is_(False),
                    Cookie.is_valid.is_(True),
                )
            )).scalar_one_or_none()

        if row is None or not is_oauth_content(row.content):
            return None

        tokens = decode_content(row.content)
        if tokens is None:
            return None

        from datetime import datetime, timezone  # noqa: PLC0415
        expires_at = datetime.fromisoformat(tokens["expires_at"])
        if expires_at <= datetime.now(timezone.utc):
            # Token expired - refresh it
            try:
                from yoink_dl.services.yttv_oauth import refresh_tokens, encode_content  # noqa: PLC0415
                tokens = await refresh_tokens(tokens)
                content = encode_content(tokens)
                now = datetime.now(timezone.utc)
                async with self._factory() as session:
                    row2 = await session.get(Cookie, row.id)
                    if row2 is not None:
                        row2.content = content
                        row2.updated_at = now
                        await session.commit()
            except Exception:
                logger.warning("OAuth token refresh failed: user=%d domain=%s", user_id, domain, exc_info=True)
                return None

        return tokens

    async def _rotate_personal_and_pool(
        self, user_id: int, domain: str, personal: Cookie, pool_cookie: Cookie
    ) -> Cookie:
        """Alternate between personal and pool cookie per user+domain."""
        key = f"personal:{user_id}:{domain}"
        with self._pool_lock:
            cycle = self._pool_iters.get(key)
            ids = [personal.id, pool_cookie.id]
            if cycle is None or cycle.ids != ids:
                cycle = _CookieCycle([personal, pool_cookie])
                self._pool_iters[key] = cycle
            return next(cycle)
