"""
Telegram upload sender.

Patterns ported from reference (all hard-won):
- video -> document fallback on timeout (3 retries, then give up and send as doc)
- caption too long: minimal caption -> no caption cascade
- RetryAfter (FloodWait): sleep + retry up to 3 times
- send_as_file: always use send_document regardless of extension
"""
from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from telegram import Bot, Message, ReplyParameters
from telegram.error import BadRequest, RetryAfter, TimedOut
from telegram.constants import ParseMode

from yoink_dl.utils.errors import DownloadError

logger = logging.getLogger(__name__)

_VIDEO_EXTS = frozenset({".mp4", ".mkv", ".webm", ".mov", ".avi", ".m4v", ".ts"})
_AUDIO_EXTS = frozenset({".mp3", ".m4a", ".ogg", ".opus", ".flac", ".wav", ".aac"})
_IMAGE_EXTS = frozenset({".jpg", ".jpeg", ".png", ".webp", ".gif"})

_MAX_CAPTION_LEN = 1024


@dataclass
class SendResult:
    message: Message
    was_document: bool = False
    caption_truncated: bool = False


@dataclass
class MediaMeta:
    duration: int = 0
    width: int = 0
    height: int = 0
    thumb: Path | None = None
    performer: str = ""
    title: str = ""


def _reply_params(reply_to: int | None) -> ReplyParameters | None:
    """Build ReplyParameters with allow_sending_without_reply=True.

    Using ReplyParameters instead of the deprecated reply_to_message_id:
    - allow_sending_without_reply=True means if the original message was
      deleted the bot still sends the file instead of raising an error.
    """
    if reply_to is None:
        return None
    return ReplyParameters(message_id=reply_to, allow_sending_without_reply=True)


async def send_file(
    bot: Bot,
    chat_id: int,
    file: Path,
    caption: str = "",
    reply_to: int | None = None,
    thread_id: int | None = None,
    meta: MediaMeta | None = None,
    send_as_file: bool = False,
    has_spoiler: bool = False,
    show_caption_above_media: bool = False,
    progress: Any | None = None,
) -> SendResult:
    m = meta or MediaMeta()
    ext = file.suffix.lower()

    common: dict[str, Any] = {"chat_id": chat_id, "parse_mode": ParseMode.HTML}
    rp = _reply_params(reply_to)
    if rp:
        common["reply_parameters"] = rp
    if thread_id:
        common["message_thread_id"] = thread_id

    async def _as_document(cap: str) -> Message:
        kw = {
            **common,
            "document": str(file),
            "filename": file.name,
            "caption": cap,
            "write_timeout": 300,
            "read_timeout": 300,
            "connect_timeout": 30,
        }
        if m.thumb:
            kw["thumbnail"] = str(m.thumb)
        return await bot.send_document(**kw)

    async def _as_video(cap: str) -> Message:
        kw = {
            **common,
            "video": str(file),
            "caption": cap,
            "supports_streaming": True,
            "write_timeout": 300,
            "read_timeout": 300,
            "connect_timeout": 30,
        }
        if m.duration:
            kw["duration"] = m.duration
        if m.width:
            kw["width"] = m.width
        if m.height:
            kw["height"] = m.height
        if m.thumb:
            kw["thumbnail"] = str(m.thumb)
            kw["cover"] = str(m.thumb)
        if has_spoiler:
            kw["has_spoiler"] = True
        if show_caption_above_media and cap:
            kw["show_caption_above_media"] = True
        return await bot.send_video(**kw)

    async def _as_audio(cap: str) -> Message:
        kw = {**common, "audio": str(file), "caption": cap, "write_timeout": 300, "read_timeout": 300}
        if m.duration:
            kw["duration"] = m.duration
        if m.performer:
            kw["performer"] = m.performer
        if m.title:
            kw["title"] = m.title
        if m.thumb:
            kw["thumbnail"] = str(m.thumb)
        return await bot.send_audio(**kw)

    async def _as_photo(cap: str) -> Message:
        kw = {**common, "photo": str(file), "caption": cap}
        if has_spoiler:
            kw["has_spoiler"] = True
        if show_caption_above_media and cap:
            kw["show_caption_above_media"] = True
        return await bot.send_photo(**kw)

    if send_as_file or ext not in (_VIDEO_EXTS | _AUDIO_EXTS | _IMAGE_EXTS):
        primary, is_doc = _as_document, True
    elif ext in _VIDEO_EXTS:
        primary, is_doc = _as_video, False
    elif ext in _AUDIO_EXTS:
        primary, is_doc = _as_audio, True
    else:
        primary, is_doc = _as_photo, True

    for cap in _caption_fallbacks(caption):
        cap_truncated = cap != caption
        try:
            result = await _retry(primary, cap, fallback=_as_document)
            if result is not None:
                _cleanup_thumb(m.thumb)
                return SendResult(message=result, was_document=is_doc, caption_truncated=cap_truncated)
        except BadRequest as e:
            if "caption" in str(e).lower() and "too long" in str(e).lower():
                continue
            raise

    # Last resort: document, no caption
    result = await _retry(_as_document, "", fallback=None)
    if result:
        _cleanup_thumb(m.thumb)
        return SendResult(message=result, was_document=True, caption_truncated=True)

    raise DownloadError(error=f"All upload strategies failed for {file.name}")


async def _retry(
    sender: Any,
    caption: str,
    fallback: Any | None,
    max_timeout: int = 3,
    max_flood: int = 3,
) -> Message | None:
    timeout_left = max_timeout
    flood_left = max_flood

    while True:
        try:
            return await sender(caption)

        except RetryAfter as e:
            flood_left -= 1
            if flood_left <= 0:
                logger.error("RetryAfter exhausted (%ds), giving up", e.retry_after)
                return None
            logger.warning("RetryAfter %ds (%d retries left)", e.retry_after, flood_left)
            await asyncio.sleep(e.retry_after)

        except (TimedOut, TimeoutError):
            timeout_left -= 1
            if timeout_left <= 0:
                if fallback and fallback is not sender:
                    try:
                        return await fallback(caption)
                    except Exception:
                        return None
                return None
            await asyncio.sleep(2)

        except BadRequest:
            raise

        except Exception as e:
            logger.error("Unexpected upload error: %s", e)
            raise


def _caption_fallbacks(caption: str) -> list[str]:
    caps = [caption]
    if len(caption) > _MAX_CAPTION_LEN:
        caps.append(caption[: _MAX_CAPTION_LEN - 1] + "…")
    return caps


def _cleanup_thumb(thumb: Path | None) -> None:
    if thumb and thumb.exists() and ".__thumb" in thumb.name:
        try:
            thumb.unlink()
        except Exception:
            pass


async def send_files(
    bot: Bot,
    chat_id: int,
    files: list[Path],
    caption: str = "",
    reply_to: int | None = None,
    thread_id: int | None = None,
    meta: MediaMeta | None = None,
    send_as_file: bool = False,
    has_spoiler: bool = False,
    show_caption_above_media: bool = False,
    progress: Any | None = None,
) -> list[SendResult]:
    results = []
    for i, file in enumerate(files):
        result = await send_file(
            bot=bot,
            chat_id=chat_id,
            file=file,
            caption=caption if i == 0 else "",
            reply_to=reply_to if i == 0 else None,
            thread_id=thread_id,
            meta=meta,
            send_as_file=send_as_file,
            has_spoiler=has_spoiler,
            show_caption_above_media=show_caption_above_media,
            progress=progress,
        )
        results.append(result)
    return results


async def send_long_title(
    bot: Bot,
    chat_id: int,
    title: str,
    reply_to: int | None = None,
    thread_id: int | None = None,
    hint: str = "",
) -> None:
    fd, tmp_str = tempfile.mkstemp(suffix=".txt", prefix="title_")
    tmp = Path(tmp_str)
    try:
        os.close(fd)
        tmp.write_text(title, encoding="utf-8")
        kw: dict[str, Any] = {
            "chat_id": chat_id,
            "document": str(tmp),
            "file_name": "full_title.txt",
            "caption": hint or "Full title",
        }
        rp = _reply_params(reply_to)
        if rp:
            kw["reply_parameters"] = rp
        if thread_id:
            kw["message_thread_id"] = thread_id
        await bot.send_document(**kw)
    except Exception as e:
        logger.warning("Failed to send long title doc: %s", e)
    finally:
        tmp.unlink(missing_ok=True)
