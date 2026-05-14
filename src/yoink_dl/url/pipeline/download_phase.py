"""Pipeline download phase: resolve URL, acquire cookies, run DownloadManager with retries."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from yoink.core.db.models import UserRole
from yoink_dl.download.manager import DownloadJob, DownloadManager
from yoink_dl.url.pipeline.helpers import _is_retryable

if TYPE_CHECKING:
    from telegram.ext import ContextTypes
    from yoink_dl.services.cookies import CookieManager
    from yoink_dl.url.domains import DomainConfig
    from yoink_dl.url.clip import ClipSpec
    from yoink_dl.bot.progress import ProgressTracker

logger = logging.getLogger(__name__)


async def acquire_cookie(
    *,
    cookie_mgr: "CookieManager | None",
    user_id: int,
    url: str,
    user_settings: Any,
    context: "ContextTypes.DEFAULT_TYPE",
    domain_cfg: "DomainConfig",
) -> "tuple[Path | None, int | None]":
    """Return (cookie_path, cookie_id) or (None, None)."""
    if not cookie_mgr:
        return None, None

    _perm_repo = context.bot_data.get("perm_repo")
    _has_pool_access = user_settings.role in (UserRole.admin, UserRole.owner)
    if not _has_pool_access and _perm_repo is not None:
        _has_pool_access = await _perm_repo.has(user_id, "dl", "shared_cookies")
    _use_pool = _has_pool_access and user_settings.use_pool_cookies

    result = await cookie_mgr.get_path_for_url(
        user_id=user_id,
        url=url,
        use_pool=_use_pool,
        no_cookie_domains=domain_cfg.no_cookie,
    )
    if result is not None:
        return result
    return None, None


async def run_with_retries(
    *,
    job: DownloadJob,
    manager: DownloadManager,
    settings: Any,
    context: "ContextTypes.DEFAULT_TYPE",
    tracker: "ProgressTracker",
    status_message: Any,
    lang: str,
) -> DownloadJob:
    """Run DownloadManager with retry logic. Returns the completed job."""
    from yoink.core.i18n import t  # noqa: PLC0415

    _bot_settings_repo = context.bot_data.get("bot_settings_repo")
    _retries_raw = None
    if _bot_settings_repo is not None:
        _retries_raw = await _bot_settings_repo.get("dl.download_retries")
    max_retries = max(1, int(_retries_raw) if _retries_raw is not None else settings.download_retries)

    for attempt in range(max_retries):
        try:
            job = await manager.run(job, progress_cb=tracker.ytdlp_hook)
            return job
        except Exception as exc:
            if not _is_retryable(exc):
                raise
            if attempt < max_retries - 1:
                logger.warning(
                    "Download attempt %d/%d failed (retrying): %s",
                    attempt + 1, max_retries, exc,
                )
                try:
                    await status_message.edit_text(
                        t("pipeline.retrying", lang,
                          attempt=attempt + 1, max=max_retries,
                          defaultValue=f"Retrying ({attempt + 1}/{max_retries})..."),
                    )
                except Exception:
                    pass
                await asyncio.sleep(2 ** attempt)
            else:
                raise

    raise RuntimeError("unreachable")


async def download(
    *,
    url: str,
    resolved: Any,
    user_id: int,
    user_settings: Any,
    settings: Any,
    download_dir: Path,
    clip: "ClipSpec | None",
    multi_clips: list,
    cookie_path: "Path | None",
    audio_only: bool,
    engine_override: Any,
    use_browser_cookies: bool,
    context: "ContextTypes.DEFAULT_TYPE",
    tracker: "ProgressTracker",
    status_message: Any,
    lang: str,
    chat_id: int,
    thread_id: int | None,
) -> DownloadJob:
    """Build DownloadJob and run it with chat action loop."""
    from telegram.constants import ChatAction  # noqa: PLC0415
    from yoink_dl.url.resolver import Engine  # noqa: PLC0415
    from yoink_dl.url.pipeline.helpers import _chat_action_loop  # noqa: PLC0415

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

    _effective_engine = engine_override or resolved.engine
    if audio_only:
        action = ChatAction.UPLOAD_VOICE
    elif user_settings.send_as_file:
        action = ChatAction.UPLOAD_DOCUMENT
    elif _effective_engine == Engine.GALLERY_DL:
        action = ChatAction.UPLOAD_PHOTO
    else:
        action = ChatAction.UPLOAD_VIDEO

    action_stop = asyncio.Event()
    action_task = asyncio.create_task(
        _chat_action_loop(context.bot, chat_id, action, thread_id, action_stop)
    )
    manager = DownloadManager(settings=settings)
    try:
        return await run_with_retries(
            job=job,
            manager=manager,
            settings=settings,
            context=context,
            tracker=tracker,
            status_message=status_message,
            lang=lang,
        )
    finally:
        action_stop.set()
        action_task.cancel()
