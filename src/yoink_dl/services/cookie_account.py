"""Fetch account info (name + avatar) from a Netscape cookie file via site APIs."""
from __future__ import annotations

import hashlib
import hmac
import logging
import time
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
_TIMEOUT = 10.0


@dataclass
class AccountInfo:
    name: str
    avatar_url: str | None = None


def _netscape_to_header(content: str) -> str:
    """Convert Netscape cookie file content to a Cookie: header string."""
    parts: list[str] = []
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        cols = line.split("\t")
        if len(cols) >= 7:
            parts.append(f"{cols[5]}={cols[6]}")
    return "; ".join(parts)


def _netscape_to_dict(content: str) -> dict[str, str]:
    d: dict[str, str] = {}
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        cols = line.split("\t")
        if len(cols) >= 7:
            d[cols[5]] = cols[6]
    return d


def _sapisid_hash(sapisid: str, origin: str) -> str:
    ts = str(int(time.time()))
    msg = f"{ts} {sapisid} {origin}".encode()
    digest = hashlib.sha1(msg).hexdigest()
    return f"SAPISIDHASH {ts}_{digest}"


async def _fetch_youtube(content: str) -> AccountInfo | None:
    cookies = _netscape_to_dict(content)
    sapisid = cookies.get("SAPISID") or cookies.get("__Secure-3PAPISID")
    if not sapisid:
        return None

    origin = "https://www.youtube.com"
    auth_header = _sapisid_hash(sapisid, origin)
    cookie_header = _netscape_to_header(content)

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                "https://www.youtube.com/youtubei/v1/account/account_menu",
                headers={
                    "Cookie": cookie_header,
                    "Authorization": auth_header,
                    "Origin": origin,
                    "User-Agent": _UA,
                    "Content-Type": "application/json",
                    "X-Youtube-Client-Name": "1",
                    "X-Youtube-Client-Version": "2.20240101.00.00",
                },
                json={
                    "context": {
                        "client": {
                            "clientName": "WEB",
                            "clientVersion": "2.20240101.00.00",
                            "hl": "en",
                        }
                    }
                },
            )
        if resp.status_code != 200:
            logger.debug("YouTube account_menu returned %d", resp.status_code)
            return None

        data = resp.json()
        renderer = (
            data.get("header", {})
            .get("activeAccountHeaderRenderer", {})
        )
        name = (
            renderer.get("accountName", {}).get("simpleText")
            or renderer.get("channelHandle", {}).get("simpleText")
        )
        thumbs = renderer.get("accountPhoto", {}).get("thumbnails", [])
        avatar = thumbs[-1]["url"] if thumbs else None

        if not name:
            return None
        return AccountInfo(name=name, avatar_url=avatar)

    except Exception:
        logger.debug("YouTube account info fetch failed", exc_info=True)
        return None


async def _fetch_instagram(content: str) -> AccountInfo | None:
    cookies = _netscape_to_dict(content)
    if "sessionid" not in cookies:
        return None
    cookie_header = _netscape_to_header(content)
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                "https://www.instagram.com/api/v1/accounts/current_user/?edit=true",
                headers={
                    "Cookie": cookie_header,
                    "User-Agent": _UA,
                    "X-IG-App-ID": "936619743392459",
                },
            )
        if resp.status_code != 200:
            return None
        data = resp.json()
        user = data.get("user", {})
        name = user.get("username") or user.get("full_name")
        avatar = user.get("profile_pic_url_hd") or user.get("profile_pic_url")
        if not name:
            return None
        return AccountInfo(name=f"@{name}", avatar_url=avatar)
    except Exception:
        logger.debug("Instagram account info fetch failed", exc_info=True)
        return None


async def _fetch_twitter(content: str) -> AccountInfo | None:
    cookies = _netscape_to_dict(content)
    if "auth_token" not in cookies:
        return None
    cookie_header = _netscape_to_header(content)
    csrf = cookies.get("ct0", "")
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                "https://api.twitter.com/1.1/account/verify_credentials.json",
                headers={
                    "Cookie": cookie_header,
                    "User-Agent": _UA,
                    "X-Csrf-Token": csrf,
                    "Authorization": "Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA",
                },
            )
        if resp.status_code != 200:
            return None
        data = resp.json()
        name = data.get("screen_name") or data.get("name")
        avatar = (data.get("profile_image_url_https") or "").replace("_normal", "")
        if not name:
            return None
        return AccountInfo(name=f"@{name}", avatar_url=avatar or None)
    except Exception:
        logger.debug("Twitter account info fetch failed", exc_info=True)
        return None


_FETCHERS = {
    "youtube.com": _fetch_youtube,
    "google.com": _fetch_youtube,
    "instagram.com": _fetch_instagram,
    "twitter.com": _fetch_twitter,
    "x.com": _fetch_twitter,
}


async def fetch_account_info(domain: str, content: str) -> AccountInfo | None:
    """
    Attempt to fetch real account name + avatar for a cookie file.
    Returns None if domain not supported or request fails.
    """
    bare = domain.removeprefix("www.")
    for d, fetcher in _FETCHERS.items():
        if bare == d or bare.endswith("." + d):
            return await fetcher(content)
    return None
