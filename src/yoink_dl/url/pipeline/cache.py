"""Pipeline cache phase: read from cache and write back after upload."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from yoink_dl.services.nsfw import NsfwChecker
from yoink_dl.upload.caption import build_caption, build_group_caption
from yoink_dl.url.pipeline.helpers import send_cached
from yoink.core.metrics import metrics

if TYPE_CHECKING:
    from telegram import Bot, Message
    from yoink_dl.storage.repos import FileCacheRepo, DownloadLogRepo
    from yoink_dl.upload.sender import SendResult

logger = logging.getLogger(__name__)


async def try_serve_from_cache(
    *,
    bot: "Bot",
    chat_id: int,
    thread_id: int | None,
    url: str,
    cache_key: str | None,
    file_cache: "FileCacheRepo | None",
    dl_log: "DownloadLogRepo | None",
    user_id: int,
    user_settings: Any,
    settings: Any,
    nsfw_checker: "NsfwChecker | None",
    is_private: bool,
    group_id: int | None,
    use_message: "Message | None",
    tg_user: Any,
) -> bool:
    """Try to serve from cache. Returns True if served (caller should return)."""
    if not cache_key or not file_cache:
        return False

    cached_group = await file_cache.get(cache_key)
    if not cached_group:
        return False

    cached = cached_group[0]
    metrics.inc("cache_hits")
    logger.info(
        "Cache hit for %s (%d item(s), file_id=%s…)",
        url, len(cached_group), cached.file_id[:12],
    )

    cached_nsfw, _ = nsfw_checker.check(url) if nsfw_checker else (False, "")

    if is_private:
        caption = build_caption(title=cached.title or "", url=url, settings=settings)
        has_spoiler = NsfwChecker.should_apply_spoiler(
            is_nsfw_content=cached_nsfw,
            user_nsfw_blur=user_settings.nsfw_blur,
            is_private_chat=True,
        )
    else:
        requester = tg_user.first_name or tg_user.username or str(user_id)
        caption = build_group_caption(url=url, requester_name=requester, requester_id=user_id)
        has_spoiler = cached_nsfw

    try:
        sent = await send_cached(
            bot=bot,
            chat_id=chat_id,
            cached=cached_group,
            caption=caption,
            reply_to=None,
            thread_id=thread_id,
            send_as_file=user_settings.send_as_file,
            has_spoiler=has_spoiler,
        )
        if dl_log:
            await dl_log.write(
                user_id, url,
                title=cached.title,
                file_size=cached.file_size,
                duration=cached.duration,
                status="cached",
                group_id=group_id,
                thread_id=thread_id,
                message_id=sent.message_id,
            )
        if not is_private and use_message:
            from yoink_dl.utils.safe_telegram import delete_many  # noqa: PLC0415
            await delete_many(bot, chat_id, [use_message.message_id])
        return True
    except Exception:
        logger.warning("Cache send failed for %s, falling through to download", url)
        return False


async def write_to_cache(
    *,
    results: "list[SendResult]",
    use_media_group: bool,
    file_cache: "FileCacheRepo | None",
    cache_key: str | None,
    job: Any,
    file_size: int,
) -> None:
    """Write upload results back to the file cache."""
    from yoink_dl.url.pipeline.helpers import _extract_file_id  # noqa: PLC0415

    if not file_cache or not cache_key:
        return

    if use_media_group:
        items = [(fid, ft) for r in results if (ex := _extract_file_id(r)) for fid, ft in [ex]]
        if items:
            try:
                await file_cache.put_group(
                    cache_key,
                    items,
                    title=job.title,
                    file_size=file_size,
                )
            except Exception as e:
                logger.warning("file_cache.put_group failed (non-fatal): %s", e)
        return

    for result in results:
        fid = _extract_file_id(result)
        if fid:
            try:
                await file_cache.put(
                    cache_key,
                    file_id=fid[0],
                    file_type=fid[1],
                    title=job.title,
                    file_size=file_size,
                    duration=job.duration,
                    url=job.resolved.url if hasattr(job, "resolved") else "",
                )
            except Exception as e:
                logger.warning("file_cache.put failed (non-fatal): %s", e)
            break
