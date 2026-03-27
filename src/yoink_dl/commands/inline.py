"""
Inline query handler - @botname <query> in any chat.

Flow (YouTube search):
  1. User types "@botname cats video" in any chat
  2. Bot searches YouTube via yt-dlp, returns up to 8 results
  3. User taps a result - Telegram sends a message with the URL
  4. Normal message handlers (_handle_url / _handle_inline_group) pick it up
     and run the standard download pipeline

Flow (direct URL):
  1. User types "@botname https://..." in any chat
  2. If file_id is cached - returns InlineQueryResultCachedVideo (instant)
  3. Otherwise - sends the URL as a message for the normal pipeline

No ChosenInlineResult handler needed - the normal pipeline handles everything
including download, upload, cache, and message cleanup.

Requires inline mode enabled via @BotFather.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
from concurrent.futures import ThreadPoolExecutor

import yt_dlp

from telegram import (
    InlineQuery,
    InlineQueryResultArticle,
    InlineQueryResultCachedVideo,
    InlineQueryResultsButton,
    InlineQueryResultVideo,
    InputTextMessageContent,
)
from telegram.ext import ContextTypes

from yoink_dl.bot.middleware import is_blocked
from yoink_dl.storage.repos import FileCacheRepo, make_cache_key

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="inline_search")

_MAX_RESULTS = 8
_MIN_QUERY_LEN = 2
_CACHE_TIME = 30


def _do_search(query: str) -> list[dict]:
    """Blocking yt-dlp YouTube search - runs in thread pool."""
    opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "skip_download": True,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(f"ytsearch{_MAX_RESULTS}:{query}", download=False)
        if not info:
            return []
        return info.get("entries") or []
    except Exception as e:
        logger.warning("Inline search failed for %r: %s", query, e)
        return []


def _fmt_duration(seconds: int | float | None) -> str:
    if not seconds:
        return ""
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{sec:02d}"
    return f"{m}:{sec:02d}"


def _best_thumbnail(entry: dict) -> str | None:
    thumbs = entry.get("thumbnails") or []
    if thumbs:
        return thumbs[-1].get("url")
    return entry.get("thumbnail")


def _make_result_id(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()[:16]


def _entry_to_result(entry: dict) -> InlineQueryResultVideo | None:
    """Convert a yt-dlp flat entry to an InlineQueryResultVideo.

    The result sends a plain URL as a text message. The normal download
    pipeline picks it up from there.
    """
    video_id = entry.get("id") or ""
    url = entry.get("url") or entry.get("webpage_url") or ""
    if not url or not url.startswith(("http://", "https://")):
        return None

    if video_id and "youtube.com" not in url and "youtu.be" not in url:
        url = f"https://www.youtube.com/watch?v={video_id}"

    title = (entry.get("title") or "Unknown")[:120]
    channel = entry.get("channel") or entry.get("uploader") or ""
    duration = _fmt_duration(entry.get("duration"))
    view_count = entry.get("view_count")

    parts: list[str] = []
    if channel:
        parts.append(channel)
    if duration:
        parts.append(duration)
    if view_count:
        if view_count >= 1_000_000:
            parts.append(f"{view_count / 1_000_000:.1f}M views")
        elif view_count >= 1_000:
            parts.append(f"{view_count // 1_000}K views")
        else:
            parts.append(f"{view_count} views")
    description = " · ".join(parts) if parts else ""

    thumbnail_url = _best_thumbnail(entry)

    return InlineQueryResultVideo(
        id=_make_result_id(url),
        title=title,
        description=description,
        video_url=url,
        mime_type="text/html",
        thumbnail_url=thumbnail_url or f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
        input_message_content=InputTextMessageContent(url),
    )


async def handle_inline(
    inline_query: InlineQuery,
    context: ContextTypes.DEFAULT_TYPE,
    query_text: str,
) -> bool:
    """Inline handler for YouTube search and direct URL downloads.

    Called by the core inline dispatcher. Returns True if the query was
    answered, False to let the next registered handler try.

    Handles:
      - Direct URLs: returns a cached file_id or an article with the URL
      - Text queries: searches YouTube via yt-dlp and returns up to 8 results
    """
    user = inline_query.from_user
    if user:
        perm_repo = context.bot_data.get("perm_repo")
        user_repo = context.bot_data.get("user_repo")
        if perm_repo and user_repo:
            u = await user_repo.get_or_create(user.id, username=user.username, first_name=user.first_name)
            allowed = await perm_repo.has(user.id, "dl", "inline", user=u)
        else:
            allowed = not await is_blocked(user.id, context)
        if not allowed:
            await inline_query.answer([], cache_time=0)
            return True

    if len(query_text) < _MIN_QUERY_LEN:
        await inline_query.answer(
            [],
            cache_time=0,
            button=InlineQueryResultsButton(
                text="Type at least 2 characters to search",
                start_parameter="search_help",
            ),
        )
        return True

    if query_text.startswith(("http://", "https://")):
        return await _handle_url_query(inline_query, context, query_text)

    loop = asyncio.get_running_loop()
    entries = await loop.run_in_executor(_executor, _do_search, query_text)

    results: list[InlineQueryResultVideo] = []
    for entry in entries:
        item = _entry_to_result(entry)
        if item:
            results.append(item)

    if not results:
        await inline_query.answer(
            [],
            cache_time=_CACHE_TIME,
            button=InlineQueryResultsButton(
                text="No results found",
                start_parameter="search_help",
            ),
        )
        return True

    await inline_query.answer(results, cache_time=_CACHE_TIME)
    return True


async def _handle_url_query(
    inline_query: InlineQuery,
    context: ContextTypes.DEFAULT_TYPE,
    url: str,
) -> bool:
    """Handle a direct URL inline query. Returns True after answering."""
    file_cache: FileCacheRepo | None = context.bot_data.get("file_cache")
    if file_cache:
        cache_key = make_cache_key(url)
        cached = await file_cache.get(cache_key) if cache_key else None
        if cached and cached.file_type == "video":
            await inline_query.answer(
                [InlineQueryResultCachedVideo(
                    id=_make_result_id(url),
                    video_file_id=cached.file_id,
                    title=cached.title or url,
                )],
                cache_time=300,
            )
            return True

    await inline_query.answer(
        [InlineQueryResultArticle(
            id=_make_result_id(url),
            title="Download this URL",
            description=url,
            input_message_content=InputTextMessageContent(url),
        )],
        cache_time=0,
    )
    return True
