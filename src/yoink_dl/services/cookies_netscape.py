"""Netscape-format cookie utilities (parse / validate / merge / extract label)."""
from __future__ import annotations

import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_DOMAIN_ALIASES: dict[str, str] = {
    "youtu.be": "youtube.com",
    "m.youtube.com": "youtube.com",
    "music.youtube.com": "youtube.com",
    "x.com": "twitter.com",
    "m.twitter.com": "twitter.com",
    "m.instagram.com": "instagram.com",
    "m.tiktok.com": "tiktok.com",
    "m.facebook.com": "facebook.com",
    "m.reddit.com": "reddit.com",
    "old.reddit.com": "reddit.com",
}


def _domain_from_url(url: str) -> str:
    host = urlparse(url).netloc.lower().split(":")[0]
    host = host.removeprefix("www.")
    return _DOMAIN_ALIASES.get(host, host)


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


def _merge_netscape_updates(content: str, updates: dict[str, str]) -> str:
    """Update values of existing cookies in a Netscape file. Does not add new lines."""
    lines = content.splitlines(keepends=True)
    result = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            result.append(line)
            continue
        parts = stripped.split("\t")
        if len(parts) >= 7 and parts[5] in updates:
            parts[6] = updates[parts[5]]
            result.append("\t".join(parts) + "\n")
        else:
            result.append(line)
    return "".join(result)


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
