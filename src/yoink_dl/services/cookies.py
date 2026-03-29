"""Cookie manager - per-user and pool Netscape cookie files stored in PostgreSQL."""
from __future__ import annotations

import itertools
import logging
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import async_sessionmaker

from yoink.core.db.models import User
from yoink_dl.storage.models import Cookie

logger = logging.getLogger(__name__)

_NETSCAPE_HEADER = "# Netscape HTTP Cookie File"


def _domain_from_url(url: str) -> str:
    host = urlparse(url).netloc.lower().split(":")[0]
    return host.removeprefix("www.")


def validate_netscape(content: str) -> bool:
    """Return True if content looks like a valid Netscape cookie file."""
    for line in content.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            if len(line.split("\t")) >= 7:
                return True
    return False


def _parse_netscape_cookies(content: str) -> dict[str, str]:
    """Parse Netscape cookie file into {name: value} dict."""
    values: dict[str, str] = {}
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) >= 7:
            values[parts[5]] = parts[6]
    return values


def extract_account_label(domain: str, content: str) -> str | None:
    """
    Extract a human-readable account label from a Netscape cookie file.
    Strategy per domain:
      - YouTube/Google: HSID fingerprint (7 chars) + timezone from PREF
      - Instagram/TikTok/Facebook/Twitter: numeric uid from identity cookie
      - Reddit: 'authenticated' if session cookie present
    Returns None if no useful info found.
    """
    bare = domain.removeprefix("www.")
    cookies = _parse_netscape_cookies(content)

    # YouTube / Google: HSID is short, stable, visually distinct
    if bare in ("youtube.com", "google.com") or bare.endswith((".youtube.com", ".google.com")):
        hsid = cookies.get("HSID")
        if hsid:
            tz_raw = ""
            pref = cookies.get("PREF", "")
            for part in pref.split("&"):
                if part.startswith("tz="):
                    tz_raw = part[3:].replace(".", "/")
                    break
            label = f"HSID:{hsid[:7]}"
            if tz_raw:
                label += f" ({tz_raw})"
            return label
        if any(k in cookies for k in ("SAPISID", "__Secure-1PSID", "SID")):
            return "authenticated"
        return None

    # Instagram
    if bare in ("instagram.com",) or bare.endswith(".instagram.com"):
        uid = cookies.get("ds_user_id")
        if uid:
            return f"uid:{uid}"
        return "authenticated" if "sessionid" in cookies else None

    # Twitter / X
    if bare in ("twitter.com", "x.com") or bare.endswith((".twitter.com", ".x.com")):
        twid = cookies.get("twid", "")
        uid = twid.replace("u%3D", "").replace("u=", "").strip()
        if uid:
            return f"uid:{uid}"
        return "authenticated" if "auth_token" in cookies else None

    # TikTok
    if bare in ("tiktok.com",) or bare.endswith(".tiktok.com"):
        uid = cookies.get("uid_tt")
        if uid:
            return f"uid:{uid[:16]}"
        return "authenticated" if "sid_tt" in cookies else None

    # Facebook
    if bare in ("facebook.com",) or bare.endswith(".facebook.com"):
        uid = cookies.get("c_user")
        if uid:
            return f"uid:{uid}"
        return "authenticated" if "xs" in cookies else None

    # Reddit
    if bare in ("reddit.com",) or bare.endswith(".reddit.com"):
        return "authenticated" if ("token_v2" in cookies or "reddit_session" in cookies) else None

    # Generic fallback: any session-like cookie
    session_hints = {"sessionid", "session", "auth_token", "access_token", "token", "sid"}
    if session_hints & set(k.lower() for k in cookies):
        return "authenticated"

    return None


def _write_tmp(content: str) -> Path:
    """Write cookie content to a temp file and return its path."""
    fd, tmp_str = tempfile.mkstemp(suffix=".txt", prefix="ck_")
    tmp = Path(tmp_str)
    try:
        os.close(fd)
        tmp.write_text(content, encoding="utf-8")
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    return tmp


def _merge_set_cookie(original: str, set_cookie_header: str) -> str:
    """
    Parse Set-Cookie header and merge updated values into a Netscape cookie file.
    Returns the updated content. Lines with expired cookies are removed.
    Unrecognised / malformed Set-Cookie values are silently ignored.
    """
    from http.cookiejar import http2time  # available in stdlib

    try:
        from set_cookie_parser import parse as _parse, split_cookie_header as _split  # type: ignore[import]
        parsed = _parse(_split(set_cookie_header), decode_values=False)
    except ImportError:
        # Fallback: skip update if library not available
        logger.debug("set-cookie-parser not installed, skipping Set-Cookie merge")
        return original

    now = datetime.now(timezone.utc)
    updates: dict[str, str] = {}
    removals: set[str] = set()

    for c in parsed:
        if c.expires and c.expires < now:
            removals.add(c.name)
        else:
            updates[c.name] = c.value

    lines = original.splitlines(keepends=True)
    new_lines: list[str] = []
    replaced: set[str] = set()

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            new_lines.append(line)
            continue
        parts = stripped.split("\t")
        if len(parts) < 7:
            new_lines.append(line)
            continue
        name = parts[5]
        if name in removals:
            continue
        if name in updates:
            parts[6] = updates[name]
            new_lines.append("\t".join(parts) + "\n")
            replaced.add(name)
        else:
            new_lines.append(line)

    # Append new cookies not already present
    for name, value in updates.items():
        if name not in replaced and name not in removals:
            # domain/path/secure/expiry unknown - use safe defaults
            new_lines.append(f".example.com\tTRUE\t/\tFALSE\t0\t{name}\t{value}\n")

    return "".join(new_lines)


class CookieManager:
    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._factory = session_factory
        # In-memory round-robin counters keyed by domain: pool cookie ids cycle
        self._pool_iters: dict[str, itertools.cycle] = {}
        self._pool_lock = threading.Lock()

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    async def _ensure_user(self, session, user_id: int) -> None:
        user = await session.get(User, user_id)
        if user is None:
            session.add(User(id=user_id))
            await session.flush()

    # ------------------------------------------------------------------ #
    # Personal cookies (user-owned, is_pool=False)
    # ------------------------------------------------------------------ #

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

    # ------------------------------------------------------------------ #
    # Pool cookies (is_pool=True, shared across users)
    # ------------------------------------------------------------------ #

    async def store_pool(self, owner_id: int, domain: str, content: str) -> Cookie:
        """Add a new pool cookie for a domain (owner/admin only)."""
        from yoink_dl.services.cookie_account import fetch_account_info  # noqa: PLC0415
        info = None
        try:
            info = await fetch_account_info(domain, content)
        except Exception:
            logger.debug("fetch_account_info failed for %s", domain, exc_info=True)

        label = (info.name if info else None) or extract_account_label(domain, content)
        avatar_url = info.avatar_url if info else None

        async with self._factory() as session:
            await self._ensure_user(session, owner_id)
            row = Cookie(user_id=owner_id, domain=domain, content=content,
                         is_valid=True, is_pool=True, label=label, avatar_url=avatar_url)
            session.add(row)
            await session.commit()
            await session.refresh(row)
        # Invalidate cached cycle for this domain
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
            await session.commit()
            row = result.fetchone()
            if row:
                with self._pool_lock:
                    self._pool_iters.pop(row[0], None)
            return result.rowcount > 0

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
                    info = await fetch_account_info(row.domain, row.content)
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
            # Rebuild cycle if ids changed (cookie added/removed)
            current_ids = [r.id for r in rows]
            if cycle is None or getattr(cycle, "_ids", None) != current_ids:
                new_cycle = itertools.cycle(rows)
                new_cycle._ids = current_ids  # type: ignore[attr-defined]
                self._pool_iters[domain] = new_cycle
                cycle = new_cycle
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

    # ------------------------------------------------------------------ #
    # Set-Cookie update (works for both personal and pool)
    # ------------------------------------------------------------------ #

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

    async def sync_from_file(self, cookie_id: int, path: Path) -> bool:
        """
        Read a cookie file (written by yt-dlp during download) and sync
        its content back to the DB row. Returns True if content changed.
        """
        try:
            new_content = path.read_text(encoding="utf-8")
        except OSError:
            return False
        async with self._factory() as session:
            row = await session.get(Cookie, cookie_id)
            if row is None:
                return False
            if new_content == row.content:
                return False
            row.content = new_content
            row.updated_at = datetime.now(timezone.utc)
            await session.commit()
        logger.debug("Synced cookie from file: id=%d path=%s", cookie_id, path)
        return True

    # ------------------------------------------------------------------ #
    # Main lookup: returns (tmp_path, cookie_id) for pipeline use
    # ------------------------------------------------------------------ #

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
          2. Pool cookie (round-robin) — only if use_pool=True
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
            row = (await session.execute(
                select(Cookie).where(
                    Cookie.user_id == user_id,
                    Cookie.domain == domain,
                    Cookie.is_valid.is_(True),
                    Cookie.is_pool.is_(False),
                )
            )).scalar_one_or_none()

        if row is None and use_pool:
            # 2. Pool cookie
            row = await self.get_pool_cookie(domain)
            if row:
                logger.debug("Using pool cookie: id=%d domain=%s user=%d", row.id, domain, user_id)

        if row is None:
            return None

        tmp = _write_tmp(row.content)
        return tmp, row.id
