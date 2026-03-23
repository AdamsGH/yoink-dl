"""
Download pipeline: orchestrates resolve → download → postprocess → upload.

Extracted from url_handler.py. Called by _run_download in handlers.py.
"""
from __future__ import annotations

import asyncio
import logging
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from telegram import Bot
from telegram.constants import ChatAction, ParseMode
from telegram.ext import ContextTypes

from yoink_dl.download.manager import DownloadJob, DownloadManager
from yoink_dl.download.postprocess import postprocess_all
from yoink_dl.services.cookies import CookieManager
from yoink_dl.services.nsfw import NsfwChecker
from yoink_dl.storage.repos import (
    CachedFile, FileCacheRepo, RateLimitRepo, DownloadLogRepo, make_cache_key,
)
from yoink_dl.upload.caption import build_caption, build_group_caption
from yoink_dl.upload.sender import MediaMeta, send_files
from yoink_dl.utils.formatting import humanbytes
from yoink_dl.utils.mediainfo import get_report as mediainfo_report
from yoink_dl.utils.safe_telegram import delete_many
from yoink.core.metrics import metrics
from yoink_dl.url.clip import ClipSpec
from yoink_dl.url.domains import DomainConfig
from yoink_dl.url.normalizer import normalize
from yoink_dl.url.resolver import resolve

if TYPE_CHECKING:
    from telegram import Update, Message
    from yoink_dl.storage.repos import UserSettingsRepo

logger = logging.getLogger(__name__)


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
    cached: CachedFile,
    caption: str,
    reply_to: int | None,
    thread_id: int | None,
    send_as_file: bool,
    has_spoiler: bool = False,
) -> Message:
    from telegram import ReplyParameters

    common: dict[str, Any] = {
        "chat_id": chat_id,
        "caption": caption,
        "parse_mode": ParseMode.HTML,
    }
    if reply_to:
        common["reply_parameters"] = ReplyParameters(
            message_id=reply_to, allow_sending_without_reply=True
        )
    if thread_id:
        common["message_thread_id"] = thread_id

    file_type = "document" if send_as_file else cached.file_type
    if file_type == "video":
        return await bot.send_video(video=cached.file_id, has_spoiler=has_spoiler, **common)
    if file_type == "audio":
        return await bot.send_audio(audio=cached.file_id, **common)
    return await bot.send_document(document=cached.file_id, **common)


def _extract_file_id(result) -> tuple[str, str] | None:
    """Return (file_id, file_type) from a SendResult, or None."""
    msg = result.message
    if msg.video:
        return msg.video.file_id, "video"
    if msg.document:
        return msg.document.file_id, "document"
    if msg.audio:
        return msg.audio.file_id, "audio"
    return None


def _fmt_sec(secs: int) -> str:
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


async def run_download(
    update: Update,
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
    from yoink.core.bot.access import role_gte
    from yoink.core.db.models import UserRole
    from yoink.core.i18n import t
    from yoink_dl.bot.middleware import get_session_factory, get_settings, get_user_repo
    from yoink_dl.bot.progress import ProgressTracker, register as reg_tracker, unregister as unreg_tracker

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

    if user_settings.blocked:
        return
    if user_settings.role == UserRole.restricted:
        if ctx_group_id is None and use_message:
            lang = user_settings.language
            await use_message.reply_html(t("start.pending", lang))
        return

    if user_id != context.bot_data["config"].owner_id:
        session_factory = get_session_factory(context)
        rl = RateLimitRepo(session_factory)
        allowed, reason = await rl.check_and_increment(
            user_id=user_id,
            limit_minute=settings.rate_limit_per_minute,
            limit_hour=settings.rate_limit_per_hour,
            limit_day=settings.rate_limit_per_day,
        )
        if not allowed:
            metrics.inc("rate_limited")
            msg_text = t("errors.rate_limited", user_settings.language) + f"\n<i>({reason})</i>"
            if use_message:
                await use_message.reply_html(msg_text)
            return

    quality_override = context.user_data.pop("_ask_quality_override", None)
    if quality_override:
        import dataclasses
        user_settings = dataclasses.replace(user_settings, quality=quality_override)

    file_cache: FileCacheRepo | None = context.bot_data.get("file_cache")
    dl_log: DownloadLogRepo | None = context.bot_data.get("download_log")
    cookie_mgr: CookieManager | None = context.bot_data.get("cookie_manager")

    domain_cfg = DomainConfig.from_config(settings)
    url = normalize(url, domain_cfg)

    is_private = (chat.type == "private") if chat else True
    group_id: int | None = ctx_group_id

    # Peek at force_mode early so cache_key includes audio/video distinction.
    # The value is popped here and must NOT be popped again later.
    force_mode = context.user_data.pop("force_mode", None)
    audio_only = force_mode == "audio"

    cache_key = make_cache_key(
        url,
        start_sec=clip.start_sec if clip else None,
        end_sec=clip.end_sec if clip else None,
        audio_only=audio_only,
    )
    if cache_key and file_cache:
        cached = await file_cache.get(cache_key)
        if cached:
            metrics.inc("cache_hits")
            logger.info("Cache hit for %s (file_id=%s…)", url, cached.file_id[:12])
            nsfw_checker: NsfwChecker | None = context.bot_data.get("nsfw_checker")
            cached_nsfw, _ = nsfw_checker.check(url) if nsfw_checker else (False, "")
            if is_private:
                cached_caption = build_caption(title=cached.title or "", url=url, settings=settings)
                cached_has_spoiler = NsfwChecker.should_apply_spoiler(
                    is_nsfw_content=cached_nsfw,
                    user_nsfw_blur=user_settings.nsfw_blur,
                    is_private_chat=True,
                )
            else:
                requester = tg_user.first_name or tg_user.username or str(user_id)
                cached_caption = build_group_caption(url=url, requester_name=requester, requester_id=user_id)
                cached_has_spoiler = cached_nsfw
            cached_reply_to = None  # user message is deleted after sending; no reply needed
            try:
                sent = await send_cached(
                    bot=context.bot,
                    chat_id=chat_id,
                    cached=cached,
                    caption=cached_caption,
                    reply_to=cached_reply_to,
                    thread_id=thread_id,
                    send_as_file=user_settings.send_as_file,
                    has_spoiler=cached_has_spoiler,
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
                    await delete_many(context.bot, chat_id, [use_message.message_id])
                return
            except Exception:
                logger.warning("Cache send failed for %s, falling through to download", url)

    metrics.inc("downloads_total")
    _dl_t0 = time.monotonic()

    lang = user_settings.language
    status_kw: dict[str, Any] = {"chat_id": chat_id, "text": t("pipeline.fetching", lang)}
    if thread_id:
        status_kw["message_thread_id"] = thread_id
    status = await context.bot.send_message(**status_kw)
    tracker = ProgressTracker(status)
    reg_tracker(tracker)
    download_dir: Path | None = None
    cookie_path: Path | None = None
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

        if cookie_mgr:
            cookie_path = await cookie_mgr.get_path_for_url(
                user_id=user_id,
                url=url,
                global_user_id=context.bot_data["config"].owner_id,
                no_cookie_domains=domain_cfg.no_cookie,
            )

        multi_clips: list = context.user_data.pop("_clips", [])

        from yoink_dl.url.resolver import Engine
        engine_override = Engine.GALLERY_DL if force_mode == "gallery" else None

        nsfw_checker = context.bot_data.get("nsfw_checker")
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
        job = DownloadJob(
            user_id=user_id,
            resolved=resolved,
            settings=user_settings,
            download_dir=download_dir,
            clip=clip,
            clips=multi_clips,
            cookie_path=cookie_path,
            audio_only=audio_only,
            engine_override=engine_override,
            use_browser_cookies=use_browser_cookies,
        )

        manager = DownloadManager(settings=settings)
        _action_stop = asyncio.Event()
        if audio_only:
            _upload_action = ChatAction.UPLOAD_VOICE
        elif user_settings.send_as_file:
            _upload_action = ChatAction.UPLOAD_DOCUMENT
        else:
            _upload_action = ChatAction.UPLOAD_VIDEO
        _action_task = asyncio.create_task(
            _chat_action_loop(context.bot, chat_id, _upload_action, thread_id, _action_stop)
        )
        try:
            job = await manager.run(job, progress_cb=tracker.ytdlp_hook)
        finally:
            _action_stop.set()
            _action_task.cancel()

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

        if is_private:
            has_spoiler = NsfwChecker.should_apply_spoiler(
                is_nsfw_content=content_is_nsfw,
                user_nsfw_blur=user_settings.nsfw_blur,
                is_private_chat=True,
            )
        else:
            has_spoiler = content_is_nsfw

        files = await postprocess_all(job.files)
        files = [f for f in files if f.exists()]
        file_size = sum(f.stat().st_size for f in files)
        logger.debug("upload: %d files, %.1fMB, chat=%d", len(files), file_size / 1e6, chat_id)

        tracker.set_phase("upload")
        await status.edit_text(t("pipeline.uploading", lang, size=humanbytes(file_size)))

        meta = MediaMeta(
            duration=int(job.duration),
            width=job.width,
            height=job.height,
            thumb=job.thumb,
        )

        if is_private:
            clip_extra = ""
            if clip:
                clip_extra = f"✂️ {_fmt_sec(clip.start_sec)} → {_fmt_sec(clip.end_sec)}"
            caption = build_caption(
                title=job.title,
                url=resolved.url,
                settings=settings,
                extra=clip_extra,
            )
            reply_to = None  # no reply in private - user message is deleted after
        else:
            requester = tg_user.first_name or tg_user.username or str(user_id)
            caption = build_group_caption(url=resolved.url, requester_name=requester, requester_id=user_id)
            reply_to = None

        results = await send_files(
            bot=context.bot,
            chat_id=chat_id,
            files=files,
            caption=caption,
            reply_to=reply_to,
            thread_id=thread_id,
            meta=meta,
            send_as_file=user_settings.send_as_file,
            has_spoiler=has_spoiler,
            show_caption_above_media=is_private,
        )

        # Delete status + user command. Send results first so reply_parameters
        # never point to a message we are about to delete.
        to_delete = [status.message_id]
        if use_message:
            to_delete.append(use_message.message_id)
        await delete_many(context.bot, chat_id, to_delete)

        if user_settings.mediainfo and len(files) == 1 and is_private:
            report = await mediainfo_report(files[0])
            if report:
                sent_id = results[0].message.message_id if results else None
                from telegram import ReplyParameters
                kw: dict = {"chat_id": chat_id, "text": report, "parse_mode": ParseMode.HTML}
                if sent_id:
                    kw["reply_parameters"] = ReplyParameters(
                        message_id=sent_id, allow_sending_without_reply=True
                    )
                if thread_id:
                    kw["message_thread_id"] = thread_id
                await context.bot.send_message(**kw)

        for result in results:
            fid = _extract_file_id(result)
            if fid and file_cache and cache_key:
                await file_cache.put(
                    cache_key,
                    file_id=fid[0],
                    file_type=fid[1],
                    title=job.title,
                    file_size=file_size,
                    duration=job.duration,
                    url=url,
                )
                break

        if dl_log:
            await dl_log.write(
                user_id, url,
                title=job.title,
                quality=user_settings.quality,
                file_size=file_size,
                duration=job.duration,
                status="ok",
                group_id=group_id,
                thread_id=thread_id,
                message_id=results[0].message.message_id if results else None,
            )

        metrics.inc("downloads_ok")
        metrics.observe("download_duration_seconds", time.monotonic() - _dl_t0)
        metrics.inc("download_bytes_total", file_size)

    except Exception as e:
        from yoink_dl.utils.errors import BotError
        metrics.inc("downloads_error")
        logger.exception("Download failed for %s: %s", url, e)
        err_text = str(e)[:300] if isinstance(e, BotError) else t("errors.unknown", "en")
        try:
            await status.edit_text(f"❌ {err_text}", parse_mode=ParseMode.HTML)
        except Exception:
            pass
        if dl_log:
            await dl_log.write(
                user_id, url=url, status="error", error_msg=str(e)[:200],
                group_id=group_id, thread_id=thread_id,
            )
        # Mark cookies invalid if error indicates auth failure
        if cookie_path is not None and cookie_mgr is not None:
            err_lower = str(e).lower()
            auth_hints = (
                "http error 403", "http error 401",
                "sign in", "log in", "login required",
                "not available", "private video",
                "cookies", "this video is private",
            )
            if any(h in err_lower for h in auth_hints):
                from yoink_dl.url.domains import extract_domain
                domain = extract_domain(resolved.url)
                if domain:
                    await cookie_mgr.mark_invalid(user_id, domain)
                    logger.info("Marked cookie invalid: user=%d domain=%s err=%s", user_id, domain, str(e)[:80])
    finally:
        unreg_tracker(tracker)
        if download_dir is not None and download_dir.exists():
            import shutil
            shutil.rmtree(download_dir, ignore_errors=True)


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
