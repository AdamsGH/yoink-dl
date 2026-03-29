"""Pipeline utility functions - chat actions, cache sending, file helpers."""
from __future__ import annotations

import asyncio
import zipfile
from pathlib import Path
from typing import Any

from telegram import Bot
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from yoink_dl.storage.repos import CachedFile


async def _chat_action_loop(
    bot: Bot,
    chat_id: int,
    action: str,
    thread_id: int | None,
    stop: asyncio.Event,
) -> None:
    """Send chat action every 4s until stop is set (Telegram clears it after 5s)."""
    kw: dict[str, Any] = {"chat_id": chat_id, "action": action}
    if thread_id:
        kw["message_thread_id"] = thread_id
    try:
        while not stop.is_set():
            try:
                await bot.send_chat_action(**kw)
            except Exception:
                pass
            await asyncio.sleep(4)
    except asyncio.CancelledError:
        pass


async def send_cached(
    bot: Bot,
    chat_id: int,
    cached: CachedFile | list[CachedFile],
    caption: str,
    reply_to: int | None,
    thread_id: int | None,
    send_as_file: bool,
    has_spoiler: bool = False,
) -> Any:
    from telegram import InputMediaDocument, InputMediaPhoto, InputMediaVideo, ReplyParameters

    common: dict[str, Any] = {"chat_id": chat_id, "parse_mode": ParseMode.HTML}
    rp = ReplyParameters(message_id=reply_to, allow_sending_without_reply=True) if reply_to else None
    if rp:
        common["reply_parameters"] = rp
    if thread_id:
        common["message_thread_id"] = thread_id

    if isinstance(cached, list) and len(cached) > 1:
        media: list[Any] = []
        for i, item in enumerate(cached):
            cap = caption if i == 0 else ""
            ftype = "document" if send_as_file else item.file_type
            if ftype == "video":
                media.append(InputMediaVideo(
                    media=item.file_id, caption=cap, parse_mode=ParseMode.HTML,
                    has_spoiler=has_spoiler or None,
                ))
            elif ftype == "photo":
                media.append(InputMediaPhoto(
                    media=item.file_id, caption=cap, parse_mode=ParseMode.HTML,
                    has_spoiler=has_spoiler or None,
                ))
            else:
                media.append(InputMediaDocument(
                    media=item.file_id, caption=cap, parse_mode=ParseMode.HTML,
                ))
        sent = await bot.send_media_group(media=media, write_timeout=120, read_timeout=120, **common)
        return sent[0]

    item = cached[0] if isinstance(cached, list) else cached
    file_type = "document" if send_as_file else item.file_type
    kw = {**common, "caption": caption}
    if file_type == "video":
        return await bot.send_video(video=item.file_id, has_spoiler=has_spoiler, **kw)
    if file_type == "audio":
        return await bot.send_audio(audio=item.file_id, **kw)
    if file_type == "photo":
        return await bot.send_photo(photo=item.file_id, has_spoiler=has_spoiler, **kw)
    return await bot.send_document(document=item.file_id, **kw)


def _extract_file_id(result: Any) -> tuple[str, str] | None:
    """Return (file_id, file_type) from a SendResult, or None."""
    msg = result.message
    if msg.video:
        return msg.video.file_id, "video"
    if msg.document:
        return msg.document.file_id, "document"
    if msg.audio:
        return msg.audio.file_id, "audio"
    if msg.photo:
        return msg.photo[-1].file_id, "photo"
    return None


_UNSAFE_CHAR_MAP = {
    '<': '＜', '>': '＞', ':': '：', '"': '＂',
    '/': '／', '\\': '＼', '|': '｜', '?': '？', '*': '＊',
}


def _safe_filename(name: str) -> str:
    """Replace Windows-unsafe characters with Unicode lookalikes, collapse whitespace."""
    import re
    name = re.sub(r'[\u0000-\u001f\u007f-\u009f]', '', name)
    for char, replacement in _UNSAFE_CHAR_MAP.items():
        name = name.replace(char, replacement)
    name = re.sub(r'\s+', ' ', name).strip()
    return name[:80] or "gallery"


async def _make_zip(files: list[Path], directory: Path, title: str = "") -> Path:
    """Pack all files into a zip archive inside directory. Runs in thread pool."""
    stem = _safe_filename(title) if title else "gallery"
    zip_path = directory / f"{stem}.zip"
    loop = asyncio.get_running_loop()

    def _build() -> None:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED) as zf:
            for f in files:
                zf.write(f, arcname=f.name)

    await loop.run_in_executor(None, _build)
    return zip_path


def _fmt_sec(secs: int) -> str:
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def _is_retryable(exc: Exception) -> bool:
    """True for transient errors worth retrying. False for auth/geo/unsupported."""
    from yoink_dl.utils.errors import (  # noqa: PLC0415
        BotError, GeoBlockedError, PrivateContentError, FileTooLargeError,
        LiveStreamError, UnsupportedUrlError, BlacklistedDomainError,
        RateLimitError, NsfwError, CookieError,
    )
    if isinstance(exc, (
        GeoBlockedError, PrivateContentError, FileTooLargeError,
        LiveStreamError, UnsupportedUrlError, BlacklistedDomainError,
        RateLimitError, NsfwError, CookieError,
    )):
        return False
    err_lower = str(exc).lower()
    no_retry_hints = (
        "http error 403", "http error 401", "http error 404",
        "sign in", "log in", "login required", "private video",
        "not available in your country", "geo",
    )
    if any(h in err_lower for h in no_retry_hints):
        return False
    retry_hints = ("exited with code", "timed out", "timeout", "connection", "reset", "broken pipe", "ssl", "network")
    if any(h in err_lower for h in retry_hints):
        return True
    from yoink_dl.utils.errors import DownloadError  # noqa: PLC0415
    if isinstance(exc, DownloadError):
        return True
    return not isinstance(exc, BotError)


_ROLE_ORDER = ["owner", "admin", "moderator", "user", "restricted", "banned"]


async def _can_use_browser_cookies(
    user_id: int,
    user_role: str,
    settings: Any,
    context: ContextTypes.DEFAULT_TYPE,
) -> bool:
    if not settings.browser_cookies_available():
        return False
    repo = context.bot_data.get("bot_settings_repo")
    if repo is None:
        return user_id == context.bot_data["config"].owner_id
    min_role = await repo.get_browser_cookies_min_role()
    min_idx = _ROLE_ORDER.index(min_role.value) if min_role.value in _ROLE_ORDER else 0
    user_idx = _ROLE_ORDER.index(user_role) if user_role in _ROLE_ORDER else len(_ROLE_ORDER)
    return user_idx <= min_idx
