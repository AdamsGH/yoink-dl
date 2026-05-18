"""Pipeline upload phase: postprocess, send files, write mediainfo."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from yoink_dl.download.postprocess import postprocess_all
from yoink_dl.upload.caption import build_caption, build_group_caption
from yoink_dl.upload.sender import MediaMeta, classify_files, send_files, send_media_group
from yoink_dl.url.pipeline.helpers import _fmt_sec, _make_zip
from yoink_dl.utils.formatting import humanbytes
from yoink.core.i18n import t

if TYPE_CHECKING:
    from pathlib import Path
    from telegram import Bot
    from telegram.ext import ContextTypes
    from yoink_dl.download.manager import DownloadJob
    from yoink_dl.url.clip import ClipSpec
    from yoink_dl.upload.sender import SendResult

logger = logging.getLogger(__name__)

_GALLERY_ZIP_THRESHOLD = 10


async def prepare_files(job: "DownloadJob") -> "tuple[list[Path], int, Any, Any]":
    """Postprocess and return (files, file_size, meta_width, meta_height)."""
    files = await postprocess_all(job.files)
    files = [f for f in files if f.exists()]
    file_size = sum(f.stat().st_size for f in files)

    meta_width = job.width
    meta_height = job.height
    if len(files) == 1 and files[0].suffix.lower() in (".mp4", ".m4v", ".mkv"):
        from yoink_dl.download.postprocess import _probe_streams  # noqa: PLC0415
        _, _, pp_w, pp_h, _ = _probe_streams(files[0])
        if pp_w and pp_h:
            meta_width, meta_height = pp_w, pp_h

    return files, file_size, meta_width, meta_height


async def get_thumbnail(job: "DownloadJob", files: list) -> "Path | None":
    """Return job thumbnail or generate one from the first video file."""
    if job.thumb is not None:
        return job.thumb
    if len(files) == 1 and files[0].suffix.lower() in (".mp4", ".m4v", ".mkv", ".webm", ".mov"):
        from yoink_dl.download.ffmpeg import make_thumbnail  # noqa: PLC0415
        return await make_thumbnail(files[0])
    return None


def build_captions(
    *,
    job: "DownloadJob",
    resolved: Any,
    is_private: bool,
    settings: Any,
    clip: "ClipSpec | None",
    tg_user: Any,
    user_id: int,
) -> str:
    if is_private:
        clip_extra = f"✂️ {_fmt_sec(clip.start_sec)} → {_fmt_sec(clip.end_sec)}" if clip else ""
        return build_caption(
            title=job.title,
            url=resolved.url,
            settings=settings,
            extra=clip_extra,
        )
    requester = tg_user.first_name or tg_user.username or str(user_id)
    return build_group_caption(url=resolved.url, requester_name=requester, requester_id=user_id)


async def send(
    *,
    bot: "Bot",
    chat_id: int,
    thread_id: int | None,
    files: list,
    caption: str,
    meta: MediaMeta,
    user_settings: Any,
    has_spoiler: bool,
    is_private: bool,
    audio_only: bool,
    download_dir: Path,
    job: "DownloadJob",
    lang: str,
    status_message: Any,
    context: "ContextTypes.DEFAULT_TYPE",
) -> "tuple[list[SendResult], bool]":
    """Send files, return (results, use_media_group)."""
    from telegram.constants import ChatAction  # noqa: PLC0415
    from yoink_dl.url.pipeline.helpers import _chat_action_loop  # noqa: PLC0415

    file_type = classify_files(files, user_settings.send_as_file)
    use_media_group = len(files) > 1 and file_type in ("image", "video", "document")
    use_zip = use_media_group and user_settings.gallery_zip and len(files) > _GALLERY_ZIP_THRESHOLD

    if audio_only:
        upload_action = ChatAction.UPLOAD_VOICE
    elif file_type == "image":
        upload_action = ChatAction.UPLOAD_PHOTO
    elif file_type == "document":
        upload_action = ChatAction.UPLOAD_DOCUMENT
    else:
        upload_action = ChatAction.UPLOAD_VIDEO

    upload_stop = asyncio.Event()
    upload_task = asyncio.create_task(
        _chat_action_loop(bot, chat_id, upload_action, thread_id, upload_stop)
    )

    await status_message.edit_text(t("pipeline.uploading", lang, size=humanbytes(sum(f.stat().st_size for f in files))))

    dl_config = context.bot_data["dl_config"]

    zip_path: Path | None = None
    try:
        if use_media_group:
            preview_files = files[:_GALLERY_ZIP_THRESHOLD - 1] if use_zip else files
            sent_messages = await send_media_group(
                bot=bot,
                chat_id=chat_id,
                files=preview_files,
                config=dl_config,
                caption=caption,
                reply_to=None,
                thread_id=thread_id,
                has_spoiler=has_spoiler,
                send_as_file=user_settings.send_as_file,
            )
            from yoink_dl.upload.sender import SendResult  # noqa: PLC0415
            results = [SendResult(message=m) for m in sent_messages]

            if use_zip:
                zip_path = await _make_zip(files, download_dir, title=job.title)
                zip_kw: dict = {
                    "chat_id": chat_id,
                    "document": str(zip_path),
                    "filename": zip_path.name,
                    "caption": f"All {len(files)} files",
                    "write_timeout": dl_config.upload_write_timeout,
                    "read_timeout": dl_config.upload_read_timeout,
                }
                if thread_id:
                    zip_kw["message_thread_id"] = thread_id
                await bot.send_document(**zip_kw)
        else:
            results = await send_files(
                bot=bot,
                chat_id=chat_id,
                files=files,
                config=dl_config,
                caption=caption,
                reply_to=None,
                thread_id=thread_id,
                meta=meta,
                send_as_file=user_settings.send_as_file,
                has_spoiler=has_spoiler,
                show_caption_above_media=is_private,
            )
    finally:
        upload_stop.set()
        upload_task.cancel()
        if zip_path and zip_path.exists():
            zip_path.unlink(missing_ok=True)

    return results, use_media_group


async def send_mediainfo(
    *,
    bot: "Bot",
    chat_id: int,
    thread_id: int | None,
    files: list,
    results: list,
    user_settings: Any,
    is_private: bool,
) -> None:
    if not (user_settings.mediainfo and len(files) == 1 and is_private):
        return
    from yoink_dl.utils.mediainfo import get_report  # noqa: PLC0415
    from telegram import ReplyParameters  # noqa: PLC0415
    from telegram.constants import ParseMode  # noqa: PLC0415

    report = await get_report(files[0])
    if not report:
        return
    sent_id = results[0].message.message_id if results else None
    kw: dict = {"chat_id": chat_id, "text": report, "parse_mode": ParseMode.HTML}
    if sent_id:
        kw["reply_parameters"] = ReplyParameters(message_id=sent_id, allow_sending_without_reply=True)
    if thread_id:
        kw["message_thread_id"] = thread_id
    await bot.send_message(**kw)
