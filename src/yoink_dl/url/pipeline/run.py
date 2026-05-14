"""run_download - download pipeline orchestrator.

Phases (each in its own module):
  guards        - rate-limit and access checks
  cache         - serve from file cache
  download_phase - resolve, cookies, DownloadManager + retries
  upload_phase  - postprocess, send, mediainfo
"""
from __future__ import annotations

import logging
import re
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from yoink.core.i18n import t
from yoink.core.metrics import metrics
from yoink_dl.storage.repos import make_cache_key
from yoink_dl.url.domains import DomainConfig
from yoink_dl.url.normalizer import normalize
from yoink_dl.url.resolver import resolve
from yoink_dl.url.clip import ClipSpec
from yoink_dl.url.pipeline.cache import try_serve_from_cache, write_to_cache
from yoink_dl.url.pipeline.download_phase import acquire_cookie, download
from yoink_dl.url.pipeline.guards import check_rate_limit, check_user_access
from yoink_dl.url.pipeline.helpers import _can_use_browser_cookies
from yoink_dl.url.pipeline.upload_phase import (
    build_captions, get_thumbnail, prepare_files, send, send_mediainfo,
)
from yoink_dl.upload.sender import MediaMeta
from yoink_dl.utils.safe_telegram import delete_many

if TYPE_CHECKING:
    from telegram import Update, Message

logger = logging.getLogger(__name__)


async def run_download(
    update: "Update",
    context: ContextTypes.DEFAULT_TYPE,
    url: str,
    clip: ClipSpec | None,
    playlist_start: int | None = None,
    playlist_end: int | None = None,
    target_chat_id: int | None = None,
) -> None:
    """
    Full download pipeline: rate-limit → cache → download → postprocess → upload.

    target_chat_id is provided when called from a callback (ask_menu, cut) so we
    send to the right chat without trying to reply to a deleted message.
    """
    from yoink_dl.bot.middleware import get_settings, get_user_repo  # noqa: PLC0415
    from yoink_dl.bot.progress import ProgressTracker, register as reg_tracker, unregister as unreg_tracker  # noqa: PLC0415

    assert update.effective_user
    tg_user = update.effective_user
    user_id = tg_user.id
    use_message = update.message
    chat = update.effective_chat
    chat_id = target_chat_id or (use_message.chat_id if use_message else None)
    assert chat_id

    settings = get_settings(context)
    user_repo = get_user_repo(context)
    msg = update.effective_message

    thread_id: int | None = None
    if msg and getattr(msg, "is_topic_message", False):
        thread_id = getattr(msg, "message_thread_id", None)
    ctx_group_id = chat.id if chat and chat.type in ("group", "supergroup") else None

    user_settings = await user_repo.get_or_create(
        user_id,
        group_id=ctx_group_id,
        first_name=tg_user.first_name,
        username=tg_user.username,
    )

    if not await check_user_access(user_settings, ctx_group_id, use_message):
        return
    if not await check_rate_limit(user_id, settings, context, user_settings, use_message):
        return

    quality_override = context.user_data.pop("_ask_quality_override", None)
    if quality_override:
        import dataclasses  # noqa: PLC0415
        user_settings = dataclasses.replace(user_settings, quality=quality_override)

    file_cache = context.bot_data.get("file_cache")
    dl_log = context.bot_data.get("download_log")
    cookie_mgr = context.bot_data.get("cookie_manager")
    nsfw_checker = context.bot_data.get("nsfw_checker")

    domain_cfg = DomainConfig.from_config(settings)
    url = normalize(url, domain_cfg)

    is_private = (chat.type == "private") if chat else True
    group_id = ctx_group_id

    force_mode = context.user_data.pop("force_mode", None)
    audio_only = force_mode == "audio"

    cache_key = make_cache_key(
        url,
        start_sec=clip.start_sec if clip else None,
        end_sec=clip.end_sec if clip else None,
        audio_only=audio_only,
    )

    if await try_serve_from_cache(
        bot=context.bot,
        chat_id=chat_id,
        thread_id=thread_id,
        url=url,
        cache_key=cache_key,
        file_cache=file_cache,
        dl_log=dl_log,
        user_id=user_id,
        user_settings=user_settings,
        settings=settings,
        nsfw_checker=nsfw_checker,
        is_private=is_private,
        group_id=group_id,
        use_message=use_message,
        tg_user=tg_user,
    ):
        return

    metrics.inc("downloads_total")
    dl_t0 = time.monotonic()
    lang = user_settings.language

    status_kw: dict[str, Any] = {"chat_id": chat_id, "text": t("pipeline.fetching", lang)}
    if thread_id:
        status_kw["message_thread_id"] = thread_id
    status = await context.bot.send_message(**status_kw)

    tracker = ProgressTracker(status)
    reg_tracker(tracker)
    download_dir: Path | None = None
    cookie_path: Path | None = None
    cookie_id: int | None = None
    resolved: Any = None

    try:
        resolved = resolve(
            url,
            domain_cfg,
            proxy_enabled=user_settings.proxy_enabled,
            custom_proxy_url=user_settings.proxy_url if user_settings.proxy_enabled else None,
            playlist_start=playlist_start,
            playlist_end=playlist_end,
        )

        cookie_path, cookie_id = await acquire_cookie(
            cookie_mgr=cookie_mgr,
            user_id=user_id,
            url=url,
            user_settings=user_settings,
            context=context,
            domain_cfg=domain_cfg,
        )

        multi_clips: list = context.user_data.pop("_clips", [])
        from yoink_dl.url.resolver import Engine  # noqa: PLC0415
        engine_override = Engine.GALLERY_DL if force_mode == "gallery" else None

        user_forced_nsfw: bool = bool(context.user_data.pop("force_nsfw", False))
        content_is_nsfw = user_forced_nsfw

        if nsfw_checker and not content_is_nsfw:
            nsfw_hit, nsfw_reason = nsfw_checker.check(url)
            if nsfw_hit:
                content_is_nsfw = True
                logger.info("nsfw pre-check: user=%d url=%s reason=%s", user_id, url, nsfw_reason)

        if content_is_nsfw and group_id and not is_private:
            group_repo = context.bot_data.get("group_repo")
            if group_repo:
                group = await group_repo.get(group_id)
                if group and not group.nsfw_allowed:
                    await status.edit_text(t("pipeline.nsfw_blocked", lang))
                    return

        use_browser_cookies = await _can_use_browser_cookies(
            user_id, user_settings.role, settings, context
        )

        download_dir = Path(tempfile.mkdtemp(prefix="yoink_"))

        job = await download(
            url=url,
            resolved=resolved,
            user_id=user_id,
            user_settings=user_settings,
            settings=settings,
            download_dir=download_dir,
            clip=clip,
            multi_clips=multi_clips,
            cookie_path=cookie_path,
            audio_only=audio_only,
            engine_override=engine_override,
            use_browser_cookies=use_browser_cookies,
            context=context,
            tracker=tracker,
            status_message=status,
            lang=lang,
            chat_id=chat_id,
            thread_id=thread_id,
        )

        if nsfw_checker and not content_is_nsfw and job.info:
            nsfw_hit, nsfw_reason = nsfw_checker.check(url, info=job.info)
            if nsfw_hit:
                content_is_nsfw = True
                logger.info("nsfw meta-check: user=%d url=%s reason=%s", user_id, url, nsfw_reason)
                if group_id and not is_private:
                    group_repo = context.bot_data.get("group_repo")
                    if group_repo:
                        group = await group_repo.get(group_id)
                        if group and not group.nsfw_allowed:
                            await status.edit_text(t("pipeline.nsfw_blocked", lang))
                            return

        from yoink_dl.services.nsfw import NsfwChecker  # noqa: PLC0415
        if is_private:
            has_spoiler = NsfwChecker.should_apply_spoiler(
                is_nsfw_content=content_is_nsfw,
                user_nsfw_blur=user_settings.nsfw_blur,
                is_private_chat=True,
            )
        else:
            has_spoiler = content_is_nsfw

        files, file_size, meta_width, meta_height = await prepare_files(job)
        logger.debug("upload: %d files, %.1fMB, chat=%d", len(files), file_size / 1e6, chat_id)

        thumb = await get_thumbnail(job, files)
        meta = MediaMeta(duration=int(job.duration), width=meta_width, height=meta_height, thumb=thumb)

        caption = build_captions(
            job=job,
            resolved=resolved,
            is_private=is_private,
            settings=settings,
            clip=clip,
            tg_user=tg_user,
            user_id=user_id,
        )

        results, use_media_group = await send(
            bot=context.bot,
            chat_id=chat_id,
            thread_id=thread_id,
            files=files,
            caption=caption,
            meta=meta,
            user_settings=user_settings,
            has_spoiler=has_spoiler,
            is_private=is_private,
            audio_only=audio_only,
            download_dir=download_dir,
            job=job,
            lang=lang,
            status_message=status,
            context=context,
        )

        to_delete = [status.message_id]
        if use_message:
            to_delete.append(use_message.message_id)
        await delete_many(context.bot, chat_id, to_delete)

        await send_mediainfo(
            bot=context.bot,
            chat_id=chat_id,
            thread_id=thread_id,
            files=files,
            results=results,
            user_settings=user_settings,
            is_private=is_private,
        )

        await write_to_cache(
            results=results,
            use_media_group=use_media_group,
            file_cache=file_cache,
            cache_key=cache_key,
            job=job,
            file_size=file_size,
        )

        if dl_log:
            await dl_log.write(
                user_id, url,
                title=job.title,
                quality=user_settings.quality,
                file_size=file_size,
                duration=job.duration,
                file_count=len(job.files) if len(job.files) > 1 else None,
                status="ok",
                group_id=group_id,
                thread_id=thread_id,
                message_id=results[0].message.message_id if results else None,
                clip_start=clip.start_sec if clip else None,
                clip_end=clip.end_sec if clip else None,
            )

        if cookie_path is not None and cookie_id is not None and cookie_mgr is not None:
            try:
                await cookie_mgr.sync_from_file(cookie_id, cookie_path)
            except Exception as e:
                logger.debug("Cookie sync failed (non-fatal): %s", e)

        metrics.inc("downloads_ok")
        metrics.observe("download_duration_seconds", time.monotonic() - dl_t0)
        metrics.inc("download_bytes_total", file_size)

    except Exception as e:
        from yoink_dl.utils.errors import BotError  # noqa: PLC0415
        metrics.inc("downloads_error")
        logger.exception("Download failed for %s: %s", url, e)

        if isinstance(e, BotError):
            err_text = t(e.message_key, lang, **e.kwargs)
        else:
            raw = re.sub(r'\x1b\[[0-9;]*m', '', str(e))
            raw = raw.removeprefix("ERROR: ")
            err_text = raw[:300] if raw else t("errors.unknown", lang)

        try:
            await status.edit_text(f"❌ {err_text}", parse_mode=ParseMode.HTML)
        except Exception:
            pass

        if dl_log:
            await dl_log.write(
                user_id, url=url, status="error", error_msg=str(e)[:200],
                group_id=group_id, thread_id=thread_id,
            )

        if cookie_id is not None and cookie_mgr is not None:
            err_lower = str(e).lower()
            auth_hints = (
                "http error 403", "http error 401",
                "sign in", "log in", "login required",
                "not available", "private video",
                "cookies", "this video is private",
                "confirm your age", "age-restricted",
            )
            if any(h in err_lower for h in auth_hints):
                try:
                    await cookie_mgr.mark_invalid(user_id, resolved.domain if resolved else "")
                except Exception:
                    pass
                try:
                    await cookie_mgr.mark_pool_invalid(cookie_id)
                except Exception:
                    pass
                logger.info("Marked cookie invalid: id=%d err=%s", cookie_id, str(e)[:80])

    finally:
        unreg_tracker(tracker)
        if download_dir is not None and download_dir.exists():
            import shutil  # noqa: PLC0415
            shutil.rmtree(download_dir, ignore_errors=True)
